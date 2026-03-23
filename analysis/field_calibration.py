"""
Calibrazione campo: homography pixel → coordinate reali (metri).
Campo FIFA standard: 105m x 68m.
"""
import json
import numpy as np
import cv2
from pathlib import Path
from typing import List, Tuple, Optional

# Coordinate campo FIFA (metri) - angoli e punti chiave
FIELD_CORNERS_FIFA = [
    (0, 0),           # angolo sx basso
    (105, 0),         # angolo dx basso
    (105, 68),        # angolo dx alto
    (0, 68),          # angolo sx alto
]

# Punti aggiuntivi opzionali (centrocampo, area rigore, ecc.)
FIELD_EXTRA_POINTS = {
    "center": (52.5, 34),
    "penalty_left": (16.5, 34),
    "penalty_right": (88.5, 34),
}


class FieldCalibrator:
    """
    Calibra il campo da coordinate pixel a metri.
    Usa cv2.findHomography per la trasformazione.
    """
    def __init__(self):
        self._pixel_points: List[Tuple[float, float]] = []
        self._field_points: List[Tuple[float, float]] = []
        self._homography: Optional[np.ndarray] = None
        self._homography_inv: Optional[np.ndarray] = None

    def add_point(self, pixel_x: float, pixel_y: float, field_x: float, field_y: float):
        """Aggiunge una corrispondenza pixel → campo."""
        self._pixel_points.append((pixel_x, pixel_y))
        self._field_points.append((field_x, field_y))
        self._homography = None  # invalida, va ricalcolata

    def clear_points(self):
        """Rimuove tutti i punti."""
        self._pixel_points.clear()
        self._field_points.clear()
        self._homography = None
        self._homography_inv = None

    def get_point_count(self) -> int:
        return len(self._pixel_points)

    def compute_homography(self) -> bool:
        """
        Calcola la matrice di homography.
        Richiede almeno 4 punti.
        """
        if len(self._pixel_points) < 4:
            return False
        src = np.array(self._pixel_points, dtype=np.float32)
        dst = np.array(self._field_points, dtype=np.float32)
        H, status = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        if H is None:
            return False
        self._homography = H
        try:
            self._homography_inv = np.linalg.inv(H)
        except np.linalg.LinAlgError:
            return False
        return True

    def pixel_to_field(self, px: float, py: float) -> Optional[Tuple[float, float]]:
        """
        Trasforma coordinate pixel → coordinate campo (metri).
        """
        if self._homography is None and not self.compute_homography():
            return None
        pt = np.array([[[px, py]]], dtype=np.float32)
        out = cv2.perspectiveTransform(pt, self._homography)
        return (float(out[0][0][0]), float(out[0][0][1]))

    def field_to_pixel(self, fx: float, fy: float) -> Optional[Tuple[float, float]]:
        """
        Trasforma coordinate campo (metri) → coordinate pixel.
        """
        if self._homography_inv is None and not self.compute_homography():
            return None
        pt = np.array([[[fx, fy]]], dtype=np.float32)
        out = cv2.perspectiveTransform(pt, self._homography_inv)
        return (float(out[0][0][0]), float(out[0][0][1]))

    def is_valid(self) -> bool:
        """True se la calibrazione è valida (homography calcolata)."""
        return self._homography is not None or (len(self._pixel_points) >= 4 and self.compute_homography())

    def save(self, path: Path) -> bool:
        """Salva calibrazione su file JSON."""
        if not self.is_valid():
            return False
        data = {
            "pixel_points": self._pixel_points,
            "field_points": self._field_points,
            "homography": self._homography.tolist() if self._homography is not None else None,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True

    @staticmethod
    def get_field_bounds(calibration_path: Path) -> Optional[Tuple[float, float, float, float]]:
        """
        Ritorna (x0, y0, x1, y1) bounding box del campo in pixel, da file calibrazione.
        None se file inesistente o < 4 punti.
        """
        if not calibration_path or not Path(calibration_path).exists():
            return None
        try:
            with open(calibration_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
        pts = data.get("pixel_points", [])
        if len(pts) < 4:
            return None
        xs = [float(p[0]) for p in pts]
        ys = [float(p[1]) for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def load(self, path: Path) -> bool:
        """Carica calibrazione da file JSON."""
        if not path.exists():
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._pixel_points = [tuple(p) for p in data["pixel_points"]]
            self._field_points = [tuple(p) for p in data["field_points"]]
            if data.get("homography"):
                self._homography = np.array(data["homography"])
                self._homography_inv = np.linalg.inv(self._homography)
            else:
                self.compute_homography()
            return True
        except Exception:
            return False
