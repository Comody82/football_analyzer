"""
Ball detection per analisi automatica.
Usa YOLOX-s (COCO class 32 = sports ball).
Riutilizza la stessa infrastruttura di player_detection.
"""
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from dataclasses import dataclass
import json

import cv2
import numpy as np


def _to_scalar(x) -> float:
    """Converte a scalare Python anche se x è un array numpy (evita WinError scalare)."""
    arr = np.asarray(x)
    return float(arr.flat[0]) if arr.size >= 1 else 0.0


# COCO class id per "sports ball"
COCO_SPORTS_BALL_CLASS_ID = 32

DETECTIONS_DIR = "detections"
BALL_DETECTIONS_FILE = "ball_detections.json"


@dataclass
class BallBox:
    x: float
    y: float
    w: float
    h: float
    confidence: float


def _get_yolox_predictor():
    """Crea/carica predictor YOLOX. Ritorna (predictor, error_msg); predictor=None se fallisce."""
    from .player_detection import PlayerDetector
    det = PlayerDetector(conf_thresh=0.25)
    if not det._init_predictor():
        return None, det.get_init_error() or "YOLOX non inizializzato."
    return det._predictor, None


def _detect_balls(frame: np.ndarray, predictor, conf_thresh: float = 0.15) -> List[BallBox]:
    """Detection palla (COCO class 32).
    Usa img_info['ratio'] per mappare le coordinate dallo spazio preprocessato al frame originale."""
    outputs, img_info = predictor.inference(frame)
    boxes = []
    if outputs is None or len(outputs) == 0:
        return boxes
    out0 = outputs[0]
    if out0 is None:
        return boxes
    ratio = float(img_info.get("ratio", 1.0)) or 1.0
    out_arr = np.asarray(out0) if not isinstance(out0, np.ndarray) else out0
    if out_arr.ndim == 1:
        out_arr = out_arr.reshape(1, -1)
    for i in range(len(out_arr)):
        out = out_arr[i]
        if len(out) < 7:
            continue
        class_id = int(_to_scalar(out[6])) if len(out) > 6 else 0
        if class_id != COCO_SPORTS_BALL_CLASS_ID:
            continue
        x1 = _to_scalar(out[0]); y1 = _to_scalar(out[1]); x2 = _to_scalar(out[2]); y2 = _to_scalar(out[3])
        obj_conf = _to_scalar(out[4])
        class_conf = _to_scalar(out[5]) if len(out) > 5 else obj_conf
        conf = obj_conf * class_conf if len(out) > 6 else obj_conf
        if conf < conf_thresh:
            continue
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        w, h = x2 - x1, y2 - y1
        if w <= 0 or h <= 0:
            continue
        x1, y1, w, h = x1 / ratio, y1 / ratio, w / ratio, h / ratio
        boxes.append(BallBox(x=x1, y=y1, w=w, h=h, confidence=conf))
    return boxes


def _apply_field_crop(
    frame: np.ndarray,
    calibration_path: Optional[str],
) -> Tuple[np.ndarray, Optional[Tuple[int, int, int, int]]]:
    """Ritaglia frame all'area campo se calibration valida. Ritorna (frame_crop, (x0,y0,x1,y1)) o (frame, None)."""
    if not calibration_path or not Path(calibration_path).exists():
        return frame, None
    try:
        from .field_calibration import FieldCalibrator
        bounds = FieldCalibrator.get_field_bounds(Path(calibration_path))
        if bounds is None:
            return frame, None
        h, w = frame.shape[:2]
        x0, y0 = max(0, int(bounds[0])), max(0, int(bounds[1]))
        x1, y1 = min(w, int(bounds[2])), min(h, int(bounds[3]))
        if x1 <= x0 or y1 <= y0:
            return frame, None
        return frame[y0:y1, x0:x1].copy(), (x0, y0, x1, y1)
    except Exception:
        return frame, None


def run_ball_detection(
    video_path: str,
    output_path: str,
    conf_thresh: float = 0.15,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    predictor=None,
    target_fps: float = 10.0,
    calibration_path: Optional[str] = None,
    checkpoint_interval: int = 0,
    first_checkpoint: int = 500,
    start_frame: int = 0,
    initial_results: Optional[dict] = None,
) -> tuple[bool, str]:
    """
    Rileva la palla in ogni frame. Salva in JSON.
    Ritorna (ok, messaggio_errore).
    target_fps: FPS target per sampling (10-12 consigliato per CPU). 0 = legacy (1 ogni 2 frame).
    calibration_path: se valido, ritaglia frame all'area campo (boost prestazioni).
    checkpoint_interval: salva ogni N frame dopo il primo (0=off). first_checkpoint: primo salvataggio.
    start_frame, initial_results: ripresa da checkpoint.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False, "Impossibile aprire il video."

    if predictor is None:
        predictor, init_err = _get_yolox_predictor()
        if predictor is None:
            cap.release()
            return False, init_err or "YOLOX non inizializzato. Installa: pip install torch torchvision yolox --no-deps"

    total = int(_to_scalar(cap.get(cv2.CAP_PROP_FRAME_COUNT))) or 0
    video_fps = _to_scalar(cap.get(cv2.CAP_PROP_FPS)) or 25.0
    if target_fps > 0 and video_fps > 0:
        frame_step = max(1, int(round(video_fps / target_fps)))
    else:
        frame_step = 2  # legacy
    total_to_process = (total + frame_step - 1) // frame_step if total > 0 else 0
    if initial_results and start_frame > 0:
        results = initial_results
        frame_idx = start_frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    else:
        results = {"frames": [], "width": 0, "height": 0, "fps": video_fps, "frame_step": frame_step, "target_fps": target_fps if target_fps > 0 else None, "crop_bounds": None}
        frame_idx = 0
    last_pct = -1
    crop_bounds = None
    processed_count = len(results.get("frames", []))

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx == 0:
                results["width"] = int(frame.shape[1])
                results["height"] = int(frame.shape[0])
                results["fps"] = _to_scalar(cap.get(cv2.CAP_PROP_FPS)) or 25.0

            frame_to_detect, crop_bounds = _apply_field_crop(frame, calibration_path)
            if frame_idx == 0 and crop_bounds is not None:
                results["crop_bounds"] = {"x0": crop_bounds[0], "y0": crop_bounds[1], "x1": crop_bounds[2], "y1": crop_bounds[3]}

            if frame_idx % frame_step == 0:
                boxes = _detect_balls(frame_to_detect, predictor, conf_thresh)
                best = max(boxes, key=lambda b: b.confidence) if boxes else None
            else:
                best = None
            if frame_idx % frame_step == 0:
                if best and crop_bounds is not None:
                    x0, y0 = crop_bounds[0], crop_bounds[1]
                    det_json = {"x": float(best.x) + float(x0), "y": float(best.y) + float(y0), "w": float(best.w), "h": float(best.h), "conf": float(best.confidence)}
                elif best:
                    det_json = {"x": float(best.x), "y": float(best.y), "w": float(best.w), "h": float(best.h), "conf": float(best.confidence)}
                else:
                    det_json = None
                frame_data = {"frame": frame_idx, "detection": det_json}
                results["frames"].append(frame_data)
                processed_count += 1

                n = len(results["frames"])
                _should_save = (
                    checkpoint_interval > 0
                    and n > 0
                    and (
                        n == first_checkpoint
                        or (n > first_checkpoint and (n - first_checkpoint) % checkpoint_interval == 0)
                    )
                )
                if _should_save:
                    ckpt_path = str(Path(output_path).with_suffix("")) + f"_checkpoint_{frame_idx}.json"
                    with open(ckpt_path, "w", encoding="utf-8") as f:
                        json.dump(results, f, indent=2)

                if total_to_process > 0 and progress_callback:
                    pct = int(100 * processed_count / total_to_process)
                    if pct != last_pct and (pct % 10 == 0 or pct >= 100):
                        progress_callback(processed_count, total_to_process, f"Frame {processed_count}/{total_to_process}")
                        last_pct = pct

            frame_idx += 1

        cap.release()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        if progress_callback and total_to_process > 0:
            progress_callback(total_to_process, total_to_process, "Completato")
        return True, ""
    except Exception as e:
        if cap.isOpened():
            cap.release()
        return False, str(e)


def get_ball_detections_path(project_analysis_dir: str) -> Path:
    from .config import get_analysis_output_path
    base = get_analysis_output_path(project_analysis_dir)
    (base / DETECTIONS_DIR).mkdir(parents=True, exist_ok=True)
    return base / DETECTIONS_DIR / BALL_DETECTIONS_FILE
