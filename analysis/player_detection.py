"""
Player detection per analisi automatica.
Usa YOLOX-s custom addestrato su dataset calcio (8 classi).
Richiede: pip install torch torchvision yolox
"""
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from dataclasses import dataclass, field
import json

import cv2
import numpy as np


def _to_scalar(x) -> float:
    """Converte a scalare Python anche se x è un array numpy (evita WinError scalare)."""
    arr = np.asarray(x)
    return float(arr.flat[0]) if arr.size >= 1 else 0.0


# Classi del modello soccer custom (8 classi)
SOCCER_CLASSES = ("Ball", "GOAL", "Goalie", "NED", "Ref", "USA", "football", "player")

# Raggruppamento classi per ruolo
PLAYER_CLASS_IDS = {2, 3, 5, 7}   # Goalie, NED (team A), USA (team B), player generico
REFEREE_CLASS_IDS = {4}            # Ref
BALL_CLASS_IDS    = {0, 6}         # Ball, football
GOAL_CLASS_IDS    = {1}            # GOAL

# Mappa class_id → stringa ruolo
CLASS_ROLE = {
    0: "ball", 1: "goal", 2: "goalie",
    3: "player", 4: "referee", 5: "player",
    6: "ball", 7: "player",
}

# Mappa class_id → squadra pre-assegnata (-1 = da classificare con KMeans)
CLASS_TEAM = {3: 0, 5: 1}  # NED=team0, USA=team1

DETECTIONS_DIR = "detections"
DETECTIONS_FILE = "player_detections.json"


@dataclass
class BoundingBox:
    x: float  # left
    y: float  # top
    w: float  # width
    h: float  # height
    confidence: float
    class_id: int = -1   # ID classe del modello soccer
    role: str = "player" # "player", "goalie", "referee", "ball", "goal"
    team: int = -1  # 0 o 1 dopo team classification, -1 = non assegnato
    jersey_hsv: Optional[Tuple[float, float, float]] = None  # (h,s,v) per clustering globale


def get_models_dir() -> Path:
    """Directory per modelli scaricati (yolox weights)."""
    import sys
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent / "models"
    else:
        base = Path(__file__).parent.parent / "models"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _get_soccer_checkpoint() -> Optional[Path]:
    """Ritorna path del checkpoint soccer custom. Cerca best_ckpt.pth in models/."""
    models_dir = get_models_dir()
    pth = models_dir / "best_ckpt.pth"
    if pth.exists():
        return pth
    return None


def _get_soccer_exp():
    """Crea exp YOLOX-S configurato per 8 classi soccer."""
    from yolox.exp import Exp
    exp = Exp()
    exp.depth = 0.33
    exp.width = 0.50
    exp.num_classes = 8
    return exp


def _detect_with_yolox(
    frame: np.ndarray,
    predictor,
    conf_thresh: float = 0.3,
) -> List[BoundingBox]:
    """Esegue detection con YOLOX Predictor su 8 classi soccer.
    Usa img_info['ratio'] per mappare le coordinate dallo spazio preprocessato a quello del frame originale."""
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
        x1 = _to_scalar(out[0]); y1 = _to_scalar(out[1]); x2 = _to_scalar(out[2]); y2 = _to_scalar(out[3])
        obj_conf = _to_scalar(out[4])
        class_conf = _to_scalar(out[5]) if len(out) > 5 else obj_conf
        class_id = int(_to_scalar(out[6])) if len(out) > 6 else 0
        conf = obj_conf * class_conf if len(out) > 6 else obj_conf
        if conf < conf_thresh:
            continue
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        w, h = x2 - x1, y2 - y1
        if w <= 0 or h <= 0:
            continue
        x1, y1, w, h = x1 / ratio, y1 / ratio, w / ratio, h / ratio
        role = CLASS_ROLE.get(class_id, "player")
        team = CLASS_TEAM.get(class_id, -1)
        boxes.append(BoundingBox(x=x1, y=y1, w=w, h=h, confidence=conf, class_id=class_id, role=role, team=team))
    return boxes


class PlayerDetector:
    """
    Rileva giocatori e oggetti nei frame video usando YOLOX-s custom (8 classi soccer).
    Classi: Ball, GOAL, Goalie, NED, Ref, USA, football, player.
    Richiede: pip install torch torchvision yolox + models/best_ckpt.pth.
    """

    def __init__(self, conf_thresh: float = 0.5, device: str = "auto"):
        self.conf_thresh = conf_thresh
        self._predictor = None
        self._device = device
        self._init_error = None

    def _init_predictor(self) -> bool:
        if self._predictor is not None:
            return True
        if self._init_error:
            return False
        try:
            from yolox.tools.demo import Predictor

            exp = _get_soccer_exp()
            model = exp.get_model()
            ckpt_path = _get_soccer_checkpoint()
            if not ckpt_path:
                self._init_error = "Checkpoint soccer non trovato: models/best_ckpt.pth"
                return False
            import torch
            ckpt = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
            if "model" in ckpt:
                model.load_state_dict(ckpt["model"], strict=False)
            else:
                model.load_state_dict(ckpt, strict=False)
            model.eval()
            dev = self._device
            if dev == "auto":
                dev = "cuda" if torch.cuda.is_available() else "cpu"
            self._predictor = Predictor(
                model,
                exp,
                SOCCER_CLASSES,
                trt_file=None,
                decoder=None,
                device=dev,
                fp16=False,
                legacy=False,
            )
            return True
        except ImportError as e:
            self._init_error = f"Installa YOLOX: pip install torch torchvision yolox\n{e}"
            return False
        except Exception as e:
            self._init_error = str(e)
            return False

    def get_init_error(self) -> Optional[str]:
        return self._init_error

    def detect(self, frame: np.ndarray) -> List[BoundingBox]:
        """Rileva persone nel frame. frame: BGR (OpenCV)."""
        if not self._init_predictor():
            return []
        return _detect_with_yolox(frame, self._predictor, self.conf_thresh)


def _filter_boxes_to_field(
    boxes: List[BoundingBox],
    width: int,
    height: int,
    crop_bounds: Optional[Tuple[int, int, int, int]],
) -> List[BoundingBox]:
    """
    Mantiene solo le detection il cui centro cade in zona campo.
    - Con calibrazione (crop): i box sono in coordinate crop; mantieni solo quelli dentro (0,0,crop_w,crop_h).
    - Senza calibrazione: escludi tribune (parte alta) e margini; zona sicura ~12-88% x, 18-92% y.
    """
    if not boxes:
        return boxes
    if crop_bounds is not None:
        x0, y0, x1, y1 = crop_bounds
        cw, ch = x1 - x0, y1 - y0
        out = []
        for b in boxes:
            cx = b.x + b.w / 2
            cy = b.y + b.h / 2
            if 0 <= cx <= cw and 0 <= cy <= ch:
                out.append(b)
        return out
    # Nessuna calibrazione: zona campo euristica (escludi tribune in alto, bordi ridotti per non tagliare giocatori)
    margin_x = 0.08
    margin_top = 0.12
    margin_bottom = 0.05
    x_min = width * margin_x
    x_max = width * (1 - margin_x)
    y_min = height * margin_top
    y_max = height * (1 - margin_bottom)
    out = []
    for b in boxes:
        cx = b.x + b.w / 2
        cy = b.y + b.h / 2
        if x_min <= cx <= x_max and y_min <= cy <= y_max:
            out.append(b)
    return out


def _apply_field_crop(
    frame: np.ndarray,
    calibration_path: Optional[str],
) -> Tuple[np.ndarray, Optional[Tuple[int, int, int, int]]]:
    """
    Ritaglia frame alla sola area campo se calibration_path valido.
    Ritorna (frame_crop, (x0,y0,x1,y1)) con offset per mappare coords. Se no crop: (frame, None).
    """
    if not calibration_path or not Path(calibration_path).exists():
        return frame, None
    try:
        from .field_calibration import FieldCalibrator
        bounds = FieldCalibrator.get_field_bounds(Path(calibration_path))
        if bounds is None:
            return frame, None
        h, w = frame.shape[:2]
        x0 = max(0, int(bounds[0]))
        y0 = max(0, int(bounds[1]))
        x1 = min(w, int(bounds[2]))
        y1 = min(h, int(bounds[3]))
        if x1 <= x0 or y1 <= y0:
            return frame, None
        return frame[y0:y1, x0:x1].copy(), (x0, y0, x1, y1)
    except Exception:
        return frame, None


def run_player_detection(
    video_path: str,
    output_path: str,
    conf_thresh: float = 0.3,
    classify_teams: bool = True,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    target_fps: float = 10.0,
    calibration_path: Optional[str] = None,
    checkpoint_interval: int = 0,
    first_checkpoint: int = 500,
    start_frame: int = 0,
    initial_results: Optional[dict] = None,
) -> Tuple[bool, str]:
    """
    Esegue player detection su tutto il video.
    Ritorna (True, "") se ok, (False, messaggio_errore) altrimenti.
    Se classify_teams=True, assegna squadra 0/1 con KMeans su colori maglia.
    Salva risultati in JSON: lista di frame, ognuno con lista di bbox (x,y,w,h,conf,team).
    target_fps: FPS target per sampling (10-12 consigliato per CPU). 0 = legacy (1 ogni 2 frame).
    calibration_path: se valido, ritaglia frame all'area campo (boost prestazioni).
    checkpoint_interval: salva ogni N frame dopo il primo (0=off). first_checkpoint: primo salvataggio.
    start_frame, initial_results: ripresa da checkpoint (frame successivo e risultati parziali).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False, "Impossibile aprire il video. Verifica che il percorso sia corretto e il file non sia corrotto."

    detector = PlayerDetector(conf_thresh=conf_thresh)
    if not detector._init_predictor():
        init_err = detector.get_init_error() or "YOLOX non disponibile"
        cap.release()
        return False, f"YOLOX non inizializzato: {init_err}"
    prev_boxes = []
    try:
        from .team_classifier import classify_teams as do_classify_teams
    except ImportError:
        do_classify_teams = None

    total = int(_to_scalar(cap.get(cv2.CAP_PROP_FRAME_COUNT))) or 0
    video_fps = _to_scalar(cap.get(cv2.CAP_PROP_FPS)) or 25.0
    if target_fps > 0 and video_fps > 0:
        frame_step = max(1, int(round(video_fps / target_fps)))
    else:
        frame_step = 2  # legacy
    total_to_process = (total + frame_step - 1) // frame_step if total > 0 else 0
    crop_bounds = None
    if initial_results and start_frame > 0:
        results = initial_results
        frame_idx = start_frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        if results.get("frames"):
            last_fd = results["frames"][-1]
            prev_boxes = [BoundingBox(x=d["x"], y=d["y"], w=d["w"], h=d["h"], confidence=d.get("conf", 0.5), class_id=d.get("class_id", -1), role=d.get("role", "player"), team=d.get("team", -1)) for d in last_fd.get("detections", [])]
        else:
            prev_boxes = []
    else:
        results = {"frames": [], "width": 0, "height": 0, "fps": video_fps, "frame_step": frame_step, "target_fps": target_fps if target_fps > 0 else None, "crop_bounds": None}
        frame_idx = 0
        prev_boxes = []
    last_pct = -1
    processed_count = len(results.get("frames", []))

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None or frame.size == 0:
                break

            if frame_idx == 0:
                results["width"] = int(frame.shape[1])
                results["height"] = int(frame.shape[0])
                results["fps"] = video_fps

            frame_to_detect, crop_bounds = _apply_field_crop(frame, calibration_path)
            if frame_idx == 0 and crop_bounds is not None:
                results["crop_bounds"] = {"x0": crop_bounds[0], "y0": crop_bounds[1], "x1": crop_bounds[2], "y1": crop_bounds[3]}

            if frame_idx % frame_step == 0:
                boxes = detector.detect(frame_to_detect)
                h_det, w_det = frame_to_detect.shape[:2]
                boxes = _filter_boxes_to_field(boxes, w_det, h_det, crop_bounds)
                prev_boxes = boxes
                if classify_teams and do_classify_teams and len(boxes) >= 2:
                    do_classify_teams(frame_to_detect, boxes)
            else:
                boxes = prev_boxes if frame_idx > 0 else []

            if frame_idx % frame_step == 0:
                def _det_to_json(b, dx=0, dy=0):
                    d = {
                        "x": float(b.x) + float(dx),
                        "y": float(b.y) + float(dy),
                        "w": float(b.w),
                        "h": float(b.h),
                        "conf": float(b.confidence),
                        "class_id": int(b.class_id),
                        "role": b.role,
                        "team": int(b.team),
                    }
                    if getattr(b, "jersey_hsv", None):
                        d["jersey_hsv"] = [float(x) for x in b.jersey_hsv]
                    return d
                if crop_bounds is not None:
                    x0, y0 = crop_bounds[0], crop_bounds[1]
                    boxes_for_json = [_det_to_json(b, x0, y0) for b in boxes]
                else:
                    boxes_for_json = [_det_to_json(b) for b in boxes]
                frame_data = {"frame": frame_idx, "detections": boxes_for_json}
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
                    if pct != last_pct and (pct % 5 == 0 or pct >= 100):
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


def get_detections_path(project_analysis_dir: str) -> Path:
    """Path file detections per progetto."""
    from .config import get_analysis_output_path
    base = get_analysis_output_path(project_analysis_dir)
    (base / DETECTIONS_DIR).mkdir(parents=True, exist_ok=True)
    return base / DETECTIONS_DIR / DETECTIONS_FILE
