"""
Video preprocessing per analisi automatica.
Downscale a 720p, FPS max 25, eventuale stabilizzazione (opzionale).
"""
import cv2
import shutil
from pathlib import Path
from typing import Callable, Optional, Tuple

from .config import MAX_RESOLUTION, MAX_FPS

PREPROCESSED_DIR = "preprocessed"
OUTPUT_FILENAME = "preprocessed.mp4"


def needs_preprocessing(
    input_path: str,
    max_resolution: Tuple[int, int] = MAX_RESOLUTION,
    max_fps: int = MAX_FPS,
) -> bool:
    """Ritorna True solo se il video supera i limiti di risoluzione o FPS."""
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        return False
    try:
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        return w > max_resolution[0] or h > max_resolution[1] or fps > max_fps
    finally:
        cap.release()


def ensure_preprocessed(
    input_path: str,
    output_path: str,
    max_resolution: Tuple[int, int] = MAX_RESOLUTION,
    max_fps: int = MAX_FPS,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> str:
    """
    Garantisce che esista un video pronto per l'analisi.
    - Se il video è già entro i limiti → copia diretta (nessuna ricodifica)
    - Se supera i limiti → preprocessing completo
    Ritorna il path del file da usare per l'analisi.
    """
    if not needs_preprocessing(input_path, max_resolution, max_fps):
        # Video già ottimizzato: copia senza ricodifica
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_path, output_path)
        if progress_callback:
            progress_callback(1, 1, "Completato")
        return output_path
    # Preprocessing necessario
    preprocess_video(input_path, output_path, max_resolution, max_fps, progress_callback)
    return output_path


def _compute_target_size(
    width: int, height: int, max_w: int, max_h: int
) -> Tuple[int, int]:
    """Calcola dimensione target mantenendo aspect ratio."""
    if width <= max_w and height <= max_h:
        return width, height
    scale = min(max_w / width, max_h / height)
    nw = int(width * scale)
    nh = int(height * scale)
    return nw, nh


def preprocess_video(
    input_path: str,
    output_path: str,
    max_resolution: Tuple[int, int] = MAX_RESOLUTION,
    max_fps: int = MAX_FPS,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> bool:
    """
    Preprocessa un video: downscale a max 720p, FPS max 25.
    Scrivi il risultato in output_path.
    progress_callback(frame_index, total_frames, message)
    """
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        return False

    try:
        in_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        in_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        in_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

        max_w, max_h = max_resolution
        out_w, out_h = _compute_target_size(in_w, in_h, max_w, max_h)
        out_fps = min(in_fps, float(max_fps))

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(output_path, fourcc, out_fps, (out_w, out_h))
        if not out.isOpened():
            return False

        # Se FPS sorgente > max, saltiamo frame per mantenere temporalità
        out_frame_step = max(1.0, in_fps / max_fps)
        last_out_idx = -1

        frame_idx = 0
        last_pct = -1

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            curr_out = int(frame_idx / out_frame_step) if out_frame_step > 1 else frame_idx
            if curr_out > last_out_idx:
                last_out_idx = curr_out
                resized = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
                out.write(resized)

                if total > 0 and progress_callback:
                    pct = int(100 * frame_idx / total)
                    if pct != last_pct and pct % 5 == 0:
                        progress_callback(frame_idx, total, f"Frame {frame_idx}/{total}")
                        last_pct = pct

            frame_idx += 1

        out.release()
        cap.release()

        if progress_callback:
            progress_callback(total, total, "Completato")

        return True
    except Exception:
        if cap.isOpened():
            cap.release()
        return False


def get_preprocessed_path(project_analysis_dir: str) -> Path:
    """Restituisce il percorso del video preprocessato per un progetto.
    project_analysis_dir = base_path / 'analysis' / project_id
    """
    from .config import get_analysis_output_path
    base = Path(get_analysis_output_path(project_analysis_dir)) / PREPROCESSED_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base / OUTPUT_FILENAME
