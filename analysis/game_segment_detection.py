"""
Game Segment Detection – rileva automaticamente i segmenti di gioco
(primo tempo, secondo tempo) senza AI pesante.

Algoritmo:
  1. Campiona 1 frame ogni SAMPLE_INTERVAL_S secondi
  2. Calcola activity_score per ogni campione:
       0.55 * motion_score + 0.45 * field_score
  3. Smoothing media mobile
  4. Trova transizioni active/inactive → segmenti
  5. Scarta segmenti < MIN_SEGMENT_S (rumori/riscaldamento)
"""
import cv2
import numpy as np
from typing import Optional, Callable

SAMPLE_INTERVAL_S = 2.0      # campiona 1 frame ogni N secondi
MIN_SEGMENT_S     = 120      # scarta segmenti più corti di 2 minuti
ACTIVITY_THRESHOLD = 0.28    # sotto = inattivo (intervallo, pre-partita)
SMOOTH_WINDOW     = 6        # finestra smoothing (campioni)
_LABELS = ['first_half', 'second_half', 'extra_time_1', 'extra_time_2']


def _activity_score(frame, prev_gray) -> tuple:
    """Ritorna (score, gray) dove gray è riusabile come prev_gray."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Motion: differenza rispetto al frame precedente (normalizzata 0-1)
    if prev_gray is not None:
        diff = cv2.absdiff(gray, prev_gray)
        motion = min(1.0, float(np.mean(diff)) / 40.0)
    else:
        motion = 0.0

    # Field: percentuale di pixel verdi (erba)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (32, 35, 35), (92, 255, 255))
    field = min(1.0, float(np.count_nonzero(green)) / (frame.shape[0] * frame.shape[1]) * 2.2)

    return min(1.0, 0.55 * motion + 0.45 * field), gray


def detect_game_segments(
    video_path: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """
    Analizza il video e rileva i segmenti di gioco attivi.

    Returns:
        {
          'segments': [{'start_ms', 'end_ms', 'label', 'duration_s'}, ...],
          'times_ms':  [int, ...],     # timestamp di ogni campione
          'scores':    [float, ...],   # activity score smussato per ogni campione
          'duration_ms': int,
        }
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {'segments': [], 'times_ms': [], 'scores': [], 'duration_ms': 0}

    fps          = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_ms  = int(total_frames / fps * 1000)
    step_frames  = max(1, int(fps * SAMPLE_INTERVAL_S))
    total_samples = max(1, total_frames // step_frames)

    times_ms  = []
    raw_scores = []
    prev_gray  = None
    sample_idx = 0

    frame_pos = 0
    while frame_pos < total_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
        ret, frame = cap.read()
        if not ret:
            break

        score, prev_gray = _activity_score(frame, prev_gray)
        times_ms.append(int(frame_pos / fps * 1000))
        raw_scores.append(score)

        frame_pos += step_frames
        sample_idx += 1
        if progress_cb and sample_idx % 8 == 0:
            progress_cb(sample_idx, total_samples)

    cap.release()

    if not times_ms:
        return {'segments': [], 'times_ms': [], 'scores': [], 'duration_ms': duration_ms}

    # Smoothing media mobile
    w = SMOOTH_WINDOW
    smoothed = []
    for i in range(len(raw_scores)):
        lo = max(0, i - w)
        hi = min(len(raw_scores), i + w + 1)
        smoothed.append(float(np.mean(raw_scores[lo:hi])))

    # Trova transizioni → segmenti grezzi
    active = [s >= ACTIVITY_THRESHOLD for s in smoothed]
    segments_raw = []
    in_seg = False
    seg_start = 0
    for i, a in enumerate(active):
        if a and not in_seg:
            seg_start = times_ms[i]
            in_seg = True
        elif not a and in_seg:
            segments_raw.append({'start_ms': seg_start, 'end_ms': times_ms[i]})
            in_seg = False
    if in_seg:
        segments_raw.append({'start_ms': seg_start, 'end_ms': duration_ms})

    # Filtra segmenti troppo corti
    segments_raw = [s for s in segments_raw
                    if (s['end_ms'] - s['start_ms']) >= MIN_SEGMENT_S * 1000]

    # Etichetta (max 4 segmenti)
    segments = []
    for i, seg in enumerate(segments_raw[:4]):
        dur_s = (seg['end_ms'] - seg['start_ms']) / 1000.0
        segments.append({
            'start_ms':  seg['start_ms'],
            'end_ms':    seg['end_ms'],
            'label':     _LABELS[i],
            'duration_s': round(dur_s, 1),
        })

    return {
        'segments':    segments,
        'times_ms':    times_ms,
        'scores':      smoothed,
        'duration_ms': duration_ms,
    }


def cut_and_merge_segments(
    video_path: str,
    segments: list,
    output_path: str,
) -> tuple:
    """
    Taglia i segmenti con FFmpeg e li unisce in un unico file.
    Ritorna (success: bool, error_msg: str).
    Se c'è un solo segmento usa -c copy diretto.
    Se ci sono più segmenti usa il concat demuxer.
    """
    import subprocess, tempfile, os
    from pathlib import Path

    if not segments:
        return False, "Nessun segmento da tagliare."

    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return False, "FFmpeg non trovato. Installa FFmpeg e aggiungilo al PATH."

    try:
        if len(segments) == 1:
            seg = segments[0]
            start_s = seg['start_ms'] / 1000.0
            dur_s   = (seg['end_ms'] - seg['start_ms']) / 1000.0
            cmd = [ffmpeg, '-y',
                   '-ss', f'{start_s:.3f}',
                   '-i', video_path,
                   '-t', f'{dur_s:.3f}',
                   '-c', 'copy',
                   output_path]
            r = subprocess.run(cmd, capture_output=True, timeout=600)
            if r.returncode != 0:
                return False, r.stderr.decode(errors='replace')[-400:]
            return True, ''

        # Più segmenti → taglia ciascuno in temp, poi concat
        tmp_dir = tempfile.mkdtemp()
        tmp_files = []
        for i, seg in enumerate(segments):
            tmp_out = os.path.join(tmp_dir, f'seg_{i}.mp4')
            start_s = seg['start_ms'] / 1000.0
            dur_s   = (seg['end_ms'] - seg['start_ms']) / 1000.0
            cmd = [ffmpeg, '-y',
                   '-ss', f'{start_s:.3f}',
                   '-i', video_path,
                   '-t', f'{dur_s:.3f}',
                   '-c', 'copy',
                   tmp_out]
            r = subprocess.run(cmd, capture_output=True, timeout=600)
            if r.returncode != 0:
                return False, r.stderr.decode(errors='replace')[-400:]
            tmp_files.append(tmp_out)

        # Scrivi file lista per concat
        list_path = os.path.join(tmp_dir, 'list.txt')
        with open(list_path, 'w') as f:
            for p in tmp_files:
                f.write(f"file '{p}'\n")

        cmd = [ffmpeg, '-y', '-f', 'concat', '-safe', '0',
               '-i', list_path, '-c', 'copy', output_path]
        r = subprocess.run(cmd, capture_output=True, timeout=600)

        # Pulizia temp
        for p in tmp_files:
            try: os.remove(p)
            except: pass
        try: os.remove(list_path)
        except: pass
        try: os.rmdir(tmp_dir)
        except: pass

        if r.returncode != 0:
            return False, r.stderr.decode(errors='replace')[-400:]
        return True, ''

    except subprocess.TimeoutExpired:
        return False, "FFmpeg timeout (video troppo lungo?)."
    except Exception as e:
        return False, str(e)


def _find_ffmpeg() -> Optional[str]:
    """Trova ffmpeg nel PATH o in posizioni comuni."""
    import shutil, os
    found = shutil.which('ffmpeg')
    if found:
        return found
    candidates = [
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None
