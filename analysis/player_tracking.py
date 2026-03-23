"""
Player tracking per analisi automatica.
Associa le stesse persone tra frame consecutivi (track_id stabile).
Usa ByteTrack-style: due passaggi di associazione (alta conf poi bassa conf)
per ridurre ID switch in occlusioni, + IoU + Hungarian.
"""
import json
from collections import Counter
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

TRACKING_DIR = "detections"
TRACKING_FILE = "player_tracks.json"


@dataclass
class Track:
    track_id: int
    x: float
    y: float
    w: float
    h: float
    team: int
    age: int  # frame da ultimo match
    hits: int  # volte matchato


def _iou_box(box1: Tuple[float, float, float, float], box2: Tuple[float, float, float, float]) -> float:
    """IoU tra due box (x1, y1, x2, y2)."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    a1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    a2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0


def _box_xywh_to_x1y1x2y2(x: float, y: float, w: float, h: float) -> Tuple[float, float, float, float]:
    return (x, y, x + w, y + h)


def _match_detections_to_tracks(
    detections: List[dict],
    tracks: List[Track],
    iou_thresh: float = 0.3,
    det_indices: Optional[List[int]] = None,
    track_indices: Optional[List[int]] = None,
) -> Tuple[List[int], List[int], List[int]]:
    """
    Associa detection -> track tramite IoU (Hungarian).
    Se det_indices/track_indices sono dati, usa solo quei sottoinsiemi.
    Ritorna: (matched_det_idx, matched_track_idx, unmatched_det_idx) in termini di det_indices.
    """
    if det_indices is None:
        det_indices = list(range(len(detections)))
    if track_indices is None:
        track_indices = list(range(len(tracks)))
    if not det_indices or not track_indices:
        return [], [], list(det_indices)

    cost = np.ones((len(det_indices), len(track_indices)))
    for ii, i in enumerate(det_indices):
        d = detections[i]
        b1 = _box_xywh_to_x1y1x2y2(d["x"], d["y"], d["w"], d["h"])
        for jj, j in enumerate(track_indices):
            t = tracks[j]
            b2 = _box_xywh_to_x1y1x2y2(t.x, t.y, t.w, t.h)
            iou = _iou_box(b1, b2)
            cost[ii, jj] = 1 - iou

    row_ind, col_ind = linear_sum_assignment(cost)
    matched_det = []
    matched_trk = []
    for ii, jj in zip(row_ind, col_ind):
        if cost[ii, jj] < (1 - iou_thresh):
            matched_det.append(det_indices[ii])
            matched_trk.append(track_indices[jj])
    unmatched_det = [i for i in det_indices if i not in matched_det]
    return matched_det, matched_trk, unmatched_det


def _bytetrack_match(
    dets: List[dict],
    active_tracks: List[Track],
    iou_thresh: float = 0.3,
    high_thresh: float = 0.5,
    low_thresh: float = 0.2,
) -> Tuple[List[int], List[int], List[int], List[int]]:
    """
    ByteTrack-style: prima associa detection ad alta conf, poi le rimanenti
    a bassa conf ai track ancora non matchati. Riduce ID switch in occlusioni.
    Ritorna: (matched_det_idx, matched_track_idx, unmatched_det_idx, unmatched_track_idx).
    """
    if not dets:
        return [], [], [], list(range(len(active_tracks)))
    if not active_tracks:
        return [], [], list(range(len(dets))), []

    confs = [d.get("conf", 0.5) for d in dets]
    high_idx = [i for i in range(len(dets)) if confs[i] >= high_thresh]
    low_idx = [i for i in range(len(dets)) if low_thresh <= confs[i] < high_thresh]

    matched_det, matched_trk, unmatched_det = _match_detections_to_tracks(
        dets, active_tracks, iou_thresh, det_indices=high_idx, track_indices=list(range(len(active_tracks)))
    )
    unmatched_trk_idx = [j for j in range(len(active_tracks)) if j not in matched_trk]

    if low_idx and unmatched_trk_idx:
        remaining_low = [i for i in low_idx if i not in matched_det]
        if remaining_low and unmatched_trk_idx:
            m2_det, m2_trk, _ = _match_detections_to_tracks(
                dets, active_tracks, iou_thresh,
                det_indices=remaining_low,
                track_indices=unmatched_trk_idx,
            )
            matched_det.extend(m2_det)
            matched_trk.extend(m2_trk)
            for j in m2_trk:
                unmatched_trk_idx.remove(j)

    unmatched_det = [i for i in range(len(dets)) if i not in matched_det]
    return matched_det, matched_trk, unmatched_det, unmatched_trk_idx


def run_player_tracking(
    detections_path: str,
    output_path: str,
    max_age: int = 30,
    iou_thresh: float = 0.3,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> bool:
    """
    Esegue tracking sulle detection. Legge player_detections.json,
    associa track_id e salva in player_tracks.json.
    """
    if not Path(detections_path).exists():
        return False

    with open(detections_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    frames_data = data.get("frames", [])
    if not frames_data:
        return False

    width = data.get("width", 0)
    height = data.get("height", 0)
    fps = data.get("fps", 25.0)
    total = len(frames_data)
    next_track_id = 0
    active_tracks: List[Track] = []

    results = {"frames": [], "width": width, "height": height, "fps": fps, "tracks": {}}
    last_pct = -1

    for frame_idx, frame_data in enumerate(frames_data):
        detections = frame_data.get("detections", [])

        # Converti detection in formato con x,y,w,h,team,conf (e jersey_hsv se presente)
        dets = []
        for d in detections:
            det = {"x": d["x"], "y": d["y"], "w": d["w"], "h": d["h"], "team": d.get("team", -1), "conf": d.get("conf", 0.5)}
            if d.get("jersey_hsv"):
                det["jersey_hsv"] = d["jersey_hsv"]
            dets.append(det)

        # ByteTrack-style: prima alta conf, poi bassa conf per recuperare occlusioni
        matched_det_idx, matched_trk_idx, unmatched_det_idx, unmatched_trk_idx = _bytetrack_match(
            dets, active_tracks, iou_thresh=iou_thresh, high_thresh=0.5, low_thresh=0.2
        )

        new_active: List[Track] = []
        out_detections = [None] * len(detections)

        for di, ti in zip(matched_det_idx, matched_trk_idx):
            t = active_tracks[ti]
            d = dets[di]
            t.x, t.y, t.w, t.h = d["x"], d["y"], d["w"], d["h"]
            t.age = 0
            t.hits += 1
            new_active.append(t)
            out_detections[di] = {
                "x": d["x"], "y": d["y"], "w": d["w"], "h": d["h"],
                "team": d["team"],
                "track_id": t.track_id,
            }
            if d.get("jersey_hsv"):
                out_detections[di]["jersey_hsv"] = d["jersey_hsv"]
            results["tracks"][str(t.track_id)] = {"team": d["team"], "hits": t.hits}

        # Track non matched: invecchiano (solo quelli davvero non associati)
        for ti in unmatched_trk_idx:
            t = active_tracks[ti]
            t.age += 1
            if t.age <= max_age:
                new_active.append(t)

        # Nuovi track per detection non matched
        for di in unmatched_det_idx:
            d = dets[di]
            t = Track(
                track_id=next_track_id,
                x=d["x"], y=d["y"], w=d["w"], h=d["h"],
                team=d["team"],
                age=0,
                hits=1,
            )
            next_track_id += 1
            new_active.append(t)
            out_detections[di] = {
                "x": d["x"], "y": d["y"], "w": d["w"], "h": d["h"],
                "team": d["team"],
                "track_id": t.track_id,
            }
            if d.get("jersey_hsv"):
                out_detections[di]["jersey_hsv"] = d["jersey_hsv"]
            results["tracks"][str(t.track_id)] = {"team": d["team"], "hits": 1}

        active_tracks = new_active

        # Ordina output (alcune detection potrebbero essere None se matched ma ordine diverso)
        final_dets = [o for o in out_detections if o is not None]

        results["frames"].append({"frame": frame_idx, "detections": final_dets})

        if progress_callback and total > 0:
            pct = int(100 * (frame_idx + 1) / total)
            if pct != last_pct and pct % 10 == 0:
                progress_callback(frame_idx + 1, total, f"Frame {frame_idx + 1}/{total}")
                last_pct = pct

    # Stabilizza team per track_id: usa la moda (team più frequente) su tutti i frame
    track_teams: Dict[int, List[int]] = {}
    for fd in results["frames"]:
        for d in fd.get("detections", []):
            tid = d.get("track_id", -1)
            t = d.get("team", -1)
            if tid not in track_teams:
                track_teams[tid] = []
            track_teams[tid].append(t)
    track_mode: Dict[int, int] = {}
    for tid, teams in track_teams.items():
        cnt = Counter(teams)
        track_mode[tid] = cnt.most_common(1)[0][0]

    for fd in results["frames"]:
        for d in fd.get("detections", []):
            tid = d.get("track_id", -1)
            if tid in track_mode:
                d["team"] = track_mode[tid]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    if progress_callback:
        progress_callback(total, total, "Completato")
    return True


def get_tracks_path(project_analysis_dir: str) -> Path:
    """Path file tracking per progetto."""
    from .config import get_analysis_output_path
    base = get_analysis_output_path(project_analysis_dir)
    (base / TRACKING_DIR).mkdir(parents=True, exist_ok=True)
    return base / TRACKING_DIR / TRACKING_FILE
