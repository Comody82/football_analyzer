"""
Ball tracking: associa la palla tra frame consecutivi.
Riutilizza la logica IoU di player_tracking adattata per 0-1 detection per frame.
"""
import json
from pathlib import Path
from typing import Callable, Optional

BALL_TRACKING_FILE = "ball_tracks.json"


def _iou_box(b1: tuple, b2: tuple) -> float:
    x1 = max(b1[0], b2[0])
    y1 = max(b1[1], b2[1])
    x2 = min(b1[2], b2[2])
    y2 = min(b1[3], b2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0


def run_ball_tracking(
    ball_detections_path: str,
    output_path: str,
    max_age: int = 15,
    iou_thresh: float = 0.2,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> bool:
    """
    Traccia la palla sui risultati di ball_detection.
    Output: ball_tracks.json con track_id per frame.
    """
    if not Path(ball_detections_path).exists():
        return False

    with open(ball_detections_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    frames_data = data.get("frames", [])
    if not frames_data:
        return False

    width = data.get("width", 0)
    height = data.get("height", 0)
    fps = data.get("fps", 25.0)
    total = len(frames_data)
    next_track_id = 0
    active_track = None  # massimo 1 track per palla
    results = {"frames": [], "width": width, "height": height, "fps": fps}
    last_pct = -1

    for frame_idx, frame_data in enumerate(frames_data):
        det = frame_data.get("detection")
        dets = [det] if det else []

        out_det = None
        if dets:
            d = dets[0]
            bx = (d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"])
            if active_track is not None:
                tb = (active_track.x, active_track.y, active_track.x + active_track.w, active_track.y + active_track.h)
                if _iou_box(bx, tb) >= iou_thresh:
                    active_track.x, active_track.y = d["x"], d["y"]
                    active_track.w, active_track.h = d["w"], d["h"]
                    active_track.age = 0
                    out_det = {"x": d["x"], "y": d["y"], "w": d["w"], "h": d["h"], "track_id": active_track.track_id}
            if out_det is None:
                class _T:
                    pass
                t = _T()
                t.track_id = next_track_id
                t.x, t.y, t.w, t.h = d["x"], d["y"], d["w"], d["h"]
                t.age = 0
                next_track_id += 1
                active_track = t
                out_det = {"x": d["x"], "y": d["y"], "w": d["w"], "h": d["h"], "track_id": t.track_id}
        else:
            if active_track is not None:
                active_track.age += 1
                if active_track.age > max_age:
                    active_track = None

        results["frames"].append({"frame": frame_idx, "detection": out_det})

        if progress_callback and total > 0:
            pct = int(100 * (frame_idx + 1) / total)
            if pct != last_pct and pct % 10 == 0:
                progress_callback(frame_idx + 1, total, f"Frame {frame_idx + 1}/{total}")
                last_pct = pct

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    if progress_callback:
        progress_callback(total, total, "Completato")
    return True


def get_ball_tracks_path(project_analysis_dir: str) -> Path:
    from .config import get_analysis_output_path
    base = get_analysis_output_path(project_analysis_dir)
    (base / "detections").mkdir(parents=True, exist_ok=True)
    return base / "detections" / BALL_TRACKING_FILE
