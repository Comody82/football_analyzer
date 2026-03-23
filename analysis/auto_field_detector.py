"""
Rilevamento automatico linee campo per calibrazione TV camera.

Calcola la homography pixel→metri senza input manuale, usando visione artificiale
per rilevare le linee bianche del campo da calcio.

Supporta:
- Camera wide fissa 180° (campo completamente visibile)
- Camera TV broadcast (campo parzialmente visibile, angolazione obliqua)
- Qualsiasi angolazione purché si vedano almeno 4 linee del campo

Algoritmo:
  1. Isola il campo verde (maschera HSV)
  2. Rileva linee bianche con Hough Transform
  3. Metodo A – Contour: trova i 4 angoli del campo dal perimetro verde
  4. Metodo B – Line: intersezioni tra linee H/V → angoli del campo
  5. Calcola homography con cv2.findHomography (RANSAC)
  6. Ritorna DetectionResult con homography + confidence score
"""
import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)

# ── Dimensioni campo FIFA standard ─────────────────────────────────────────
FIELD_W = 105.0   # lunghezza in metri
FIELD_H = 68.0    # larghezza in metri

# ── Range HSV per erba verde (si adatta a diverse condizioni luminose) ──────
# Range ampio per coprire erba naturale, sintetica, diversa illuminazione
_GRASS_RANGES = [
    (np.array([28, 25, 25]),  np.array([95, 255, 255])),   # verde standard
    (np.array([20, 20, 20]),  np.array([100, 255, 255])),  # verde pallido/giallognolo
]


# ── Risultato del rilevamento ───────────────────────────────────────────────
@dataclass
class DetectionResult:
    """Risultato della rilevazione automatica della calibrazione campo."""
    homography: Optional[np.ndarray] = None
    confidence: float = 0.0            # 0.0 → 1.0
    pixel_points: List[Tuple[float, float]] = field(default_factory=list)
    field_points: List[Tuple[float, float]] = field(default_factory=list)
    method: str = "none"               # "contour" | "lines" | "none"
    error_msg: str = ""

    @property
    def is_valid(self) -> bool:
        return self.homography is not None and self.confidence > 0.25


# ── Detector principale ─────────────────────────────────────────────────────
class AutoFieldDetector:
    """
    Rilevamento automatico calibrazione campo per qualsiasi tipo di camera.

    Uso base:
        detector = AutoFieldDetector()
        result = detector.detect(frame_bgr)
        if result.is_valid:
            H = result.homography
            # usa H con cv2.perspectiveTransform(...)

    Uso avanzato (con immagini di debug):
        result, debug = detector.detect_with_debug(frame_bgr)
    """

    def __init__(self, field_w: float = FIELD_W, field_h: float = FIELD_H):
        self.field_w = field_w
        self.field_h = field_h

    # ── Entry point principale ──────────────────────────────────────────────
    def detect(self, frame: np.ndarray) -> DetectionResult:
        """
        Analizza un frame BGR e ritorna la calibrazione automatica del campo.

        Args:
            frame: Frame BGR dal video (np.ndarray HxWx3)

        Returns:
            DetectionResult con homography e confidence score
        """
        if frame is None or frame.size == 0:
            return DetectionResult(error_msg="Frame vuoto")

        h, w = frame.shape[:2]

        # Maschera campo verde
        field_mask = self._detect_field_mask(frame)
        coverage = np.count_nonzero(field_mask) / (h * w)

        if coverage < 0.08:
            return DetectionResult(error_msg=f"Campo verde non trovato (copertura {coverage:.1%})")

        # Metodo A: contour (più affidabile, funziona quando si vede il perimetro del campo)
        result = self._try_contour_method(frame, field_mask, w, h)
        if result.is_valid:
            logger.debug(f"AutoFieldDetector: contour method OK conf={result.confidence:.2f}")
            return result

        # Metodo B: line-based (per TV camera con angolazione parziale)
        result = self._try_line_method(frame, field_mask, w, h)
        if result.is_valid:
            logger.debug(f"AutoFieldDetector: line method OK conf={result.confidence:.2f}")
            return result

        return DetectionResult(
            error_msg="Impossibile rilevare automaticamente il campo. "
                      "Usa la calibrazione manuale oppure migliora l'inquadratura."
        )

    def detect_with_debug(self, frame: np.ndarray) -> Tuple[DetectionResult, dict]:
        """
        Come detect() ma ritorna anche immagini di debug per visualizzazione UI.

        Returns:
            (DetectionResult, dict) dove dict contiene:
              - 'field_mask': maschera verde (grayscale)
              - 'white_lines': maschera linee bianche (grayscale)
              - 'overlay': frame BGR con punti e quadrilatero disegnati
        """
        result = self.detect(frame)

        debug = {'field_mask': None, 'white_lines': None, 'overlay': frame.copy()}

        if frame is not None and frame.size > 0:
            field_mask = self._detect_field_mask(frame)
            debug['field_mask'] = field_mask
            debug['white_lines'] = self._detect_white_lines(frame, field_mask)

            overlay = frame.copy()
            if result.is_valid and result.pixel_points:
                pts = [(int(p[0]), int(p[1])) for p in result.pixel_points]
                for i, pt in enumerate(pts):
                    cv2.circle(overlay, pt, 8, (0, 255, 0), -1)
                    cv2.circle(overlay, pt, 10, (255, 255, 255), 2)
                    cv2.putText(overlay, f"P{i+1}", (pt[0]+12, pt[1]+5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                if len(pts) >= 4:
                    pts_arr = np.array(pts[:4], dtype=np.int32)
                    cv2.polylines(overlay, [pts_arr.reshape(-1, 1, 2)], True, (0, 255, 0), 2)
                cv2.putText(overlay,
                            f"Conf: {result.confidence:.0%}  Metodo: {result.method}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            else:
                cv2.putText(overlay, result.error_msg or "Rilevamento fallito",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            debug['overlay'] = overlay

        return result, debug

    # ── Maschera campo verde ────────────────────────────────────────────────
    def _detect_field_mask(self, frame: np.ndarray) -> np.ndarray:
        """Isola i pixel del campo verde tramite segmentazione HSV."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)

        for lower, upper in _GRASS_RANGES:
            mask |= cv2.inRange(hsv, lower, upper)

        # Pulizia morfologica
        k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        k_open  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k_close)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k_open)

        return mask

    # ── Linee bianche ───────────────────────────────────────────────────────
    def _detect_white_lines(self, frame: np.ndarray, field_mask: np.ndarray) -> np.ndarray:
        """Rileva i pixel delle linee bianche all'interno del campo."""
        masked = cv2.bitwise_and(frame, frame, mask=field_mask)
        gray   = cv2.cvtColor(masked, cv2.COLOR_BGR2GRAY)

        # Pixel bianchi sul verde: soglia alta
        _, white = cv2.threshold(gray, 165, 255, cv2.THRESH_BINARY)

        # Tieni solo i bianchi dentro la maschera campo
        white = cv2.bitwise_and(white, field_mask)

        # Chiudi piccoli buchi
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, k)

        return white

    # ── METODO A: Contour ───────────────────────────────────────────────────
    def _try_contour_method(self, frame: np.ndarray, field_mask: np.ndarray,
                            w: int, h: int) -> DetectionResult:
        """
        Trova i 4 angoli del campo dal contorno del campo verde.
        Affidabile quando il perimetro del campo è chiaramente visibile.
        """
        contours, _ = cv2.findContours(
            field_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return DetectionResult(error_msg="Contour: nessun contorno trovato")

        # Prendi il contorno più grande
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)

        # Deve coprire almeno il 15% del frame
        if area < w * h * 0.15:
            return DetectionResult(error_msg="Contour: area troppo piccola")

        # Convex hull + approssimazione a 4 punti
        hull = cv2.convexHull(largest)
        corners = self._approx_to_quad(hull)

        if corners is None or len(corners) != 4:
            return DetectionResult(error_msg="Contour: impossibile approssimare a quadrilatero")

        # Valida il quadrilatero
        if not self._validate_quad(corners, w, h):
            return DetectionResult(error_msg="Contour: quadrilatero non valido")

        return self._build_result(corners, w, h, method="contour")

    def _approx_to_quad(self, contour: np.ndarray) -> Optional[np.ndarray]:
        """Approssima un contorno a 4 punti (quadrilatero)."""
        peri = cv2.arcLength(contour, True)
        if peri == 0:
            return None

        # Prova diversi livelli di approssimazione
        for eps in [0.02, 0.04, 0.06, 0.08, 0.10, 0.13]:
            approx = cv2.approxPolyDP(contour, eps * peri, True)
            if len(approx) == 4:
                return approx.reshape(4, 2).astype(np.float32)

        # Fallback: usa i 4 punti estremi (top, right, bottom, left)
        pts = contour.reshape(-1, 2).astype(np.float32)
        if len(pts) < 4:
            return None

        top    = pts[np.argmin(pts[:, 1])]
        bottom = pts[np.argmax(pts[:, 1])]
        left   = pts[np.argmin(pts[:, 0])]
        right  = pts[np.argmax(pts[:, 0])]

        return np.array([top, right, bottom, left], dtype=np.float32)

    # ── METODO B: Line-based ────────────────────────────────────────────────
    def _try_line_method(self, frame: np.ndarray, field_mask: np.ndarray,
                         w: int, h: int) -> DetectionResult:
        """
        Rileva le linee bianche con Hough Transform e trova i 4 angoli
        tramite intersezioni tra linee orizzontali e verticali.
        Funziona anche quando il campo è parzialmente visibile (camera TV).
        """
        white_mask = self._detect_white_lines(frame, field_mask)

        min_line_len = int(min(w, h) * 0.07)  # almeno 7% della dimensione frame
        lines = cv2.HoughLinesP(
            white_mask, rho=1, theta=np.pi/180,
            threshold=35, minLineLength=min_line_len, maxLineGap=20)

        if lines is None or len(lines) < 4:
            return DetectionResult(error_msg="Lines: linee insufficienti")

        h_lines, v_lines = self._classify_lines(lines, w, h)

        if len(h_lines) < 2 or len(v_lines) < 2:
            return DetectionResult(error_msg="Lines: necessarie almeno 2H + 2V")

        # Unisci linee duplicate
        h_merged = self._merge_lines(h_lines, horizontal=True)
        v_merged = self._merge_lines(v_lines, horizontal=False)

        if len(h_merged) < 2 or len(v_merged) < 2:
            return DetectionResult(error_msg="Lines: merge fallito")

        # Prendi le 2 linee H più distanti (touchlines) e le 2 V più distanti (goal lines)
        h_sorted = sorted(h_merged, key=lambda l: (l[1] + l[3]) / 2)
        v_sorted = sorted(v_merged, key=lambda l: (l[0] + l[2]) / 2)

        top_h   = h_sorted[0]
        bot_h   = h_sorted[-1]
        left_v  = v_sorted[0]
        right_v = v_sorted[-1]

        corners_raw = [
            self._line_intersection(top_h, left_v),
            self._line_intersection(top_h, right_v),
            self._line_intersection(bot_h, right_v),
            self._line_intersection(bot_h, left_v),
        ]

        if any(c is None for c in corners_raw):
            return DetectionResult(error_msg="Lines: intersezioni non calcolabili")

        corners = np.array(corners_raw, dtype=np.float32)

        if not self._validate_quad(corners, w, h):
            return DetectionResult(error_msg="Lines: quadrilatero non valido")

        return self._build_result(corners, w, h, method="lines")

    def _classify_lines(self, lines: np.ndarray, w: int, h: int) -> Tuple[List, List]:
        """Classifica le linee in orizzontali (±25°) e verticali (±25° da 90°)."""
        h_lines, v_lines = [], []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            dx, dy = x2 - x1, y2 - y1
            length = np.hypot(dx, dy)
            if length < 10:
                continue
            angle = abs(np.degrees(np.arctan2(abs(dy), abs(dx))))
            entry = (int(x1), int(y1), int(x2), int(y2), float(length))
            if angle < 25:
                h_lines.append(entry)
            elif angle > 65:
                v_lines.append(entry)

        h_lines.sort(key=lambda l: -l[4])
        v_lines.sort(key=lambda l: -l[4])
        return h_lines, v_lines

    def _merge_lines(self, lines: List, horizontal: bool, tol: int = 40) -> List:
        """Unisce linee quasi-collineari dello stesso tipo."""
        if not lines:
            return []
        merged, used = [], [False] * len(lines)
        for i, line in enumerate(lines):
            if used[i]:
                continue
            used[i] = True
            group = [line]
            ci = (line[1] + line[3]) / 2 if horizontal else (line[0] + line[2]) / 2
            for j, other in enumerate(lines[i+1:], i+1):
                if used[j]:
                    continue
                cj = (other[1] + other[3]) / 2 if horizontal else (other[0] + other[2]) / 2
                if abs(ci - cj) < tol:
                    group.append(other)
                    used[j] = True
            merged.append(max(group, key=lambda l: l[4]))  # prendi la più lunga
        return merged

    @staticmethod
    def _line_intersection(l1: Tuple, l2: Tuple) -> Optional[Tuple[float, float]]:
        """Intersezione geometrica di due segmenti (estesi come rette)."""
        x1, y1, x2, y2 = l1[0], l1[1], l1[2], l1[3]
        x3, y3, x4, y4 = l2[0], l2[1], l2[2], l2[3]
        denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
        if abs(denom) < 1e-9:
            return None
        t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / denom
        return (x1 + t*(x2-x1), y1 + t*(y2-y1))

    # ── Helpers comuni ──────────────────────────────────────────────────────
    def _validate_quad(self, corners: np.ndarray, w: int, h: int) -> bool:
        """Verifica che il quadrilatero sia plausibile come campo da calcio."""
        # Area minima: 10% del frame
        area = cv2.contourArea(corners.reshape(-1, 1, 2).astype(np.int32))
        if area < w * h * 0.10:
            return False

        # Tutti i punti devono stare in un range ragionevole (con margine 50%)
        for px, py in corners:
            if not (-w*0.5 < px < w*1.5 and -h*0.5 < py < h*1.5):
                return False

        # Aspect ratio plausibile per un campo: larghezza > altezza (tipicamente 1.4:1 – 2:1)
        xs = corners[:, 0]
        ys = corners[:, 1]
        quad_w = xs.max() - xs.min()
        quad_h = ys.max() - ys.min()
        if quad_h == 0:
            return False
        ratio = quad_w / quad_h
        if not (0.5 < ratio < 6.0):  # range ampio per gestire angolazioni estreme
            return False

        return True

    def _order_corners(self, corners: np.ndarray) -> np.ndarray:
        """Ordina i 4 angoli come: TL, TR, BR, BL."""
        rect = np.zeros((4, 2), dtype=np.float32)
        s    = corners.sum(axis=1)
        diff = np.diff(corners, axis=1).squeeze()
        rect[0] = corners[np.argmin(s)]     # TL: x+y minimo
        rect[2] = corners[np.argmax(s)]     # BR: x+y massimo
        rect[1] = corners[np.argmin(diff)]  # TR: x-y minimo
        rect[3] = corners[np.argmax(diff)]  # BL: x-y massimo
        return rect

    def _build_result(self, corners: np.ndarray, w: int, h: int,
                      method: str) -> DetectionResult:
        """
        Costruisce il DetectionResult dalla lista di 4 angoli (pixel) del campo.
        Mappa nell'ordine TL→TR→BR→BL.
        """
        ordered = self._order_corners(corners)

        pixel_pts = [tuple(p) for p in ordered]
        field_pts = [
            (0.0,         0.0),
            (self.field_w, 0.0),
            (self.field_w, self.field_h),
            (0.0,         self.field_h),
        ]

        src = ordered
        dst = np.array(field_pts, dtype=np.float32)

        H, mask_ransac = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        if H is None:
            return DetectionResult(error_msg=f"{method}: findHomography fallita")

        inliers = int(mask_ransac.sum()) if mask_ransac is not None else 4
        confidence = self._compute_confidence(H, pixel_pts, field_pts, w, h, inliers)

        return DetectionResult(
            homography=H,
            confidence=confidence,
            pixel_points=pixel_pts,
            field_points=field_pts,
            method=method,
        )

    def _compute_confidence(self, H: np.ndarray,
                            pixel_pts: List[Tuple[float, float]],
                            field_pts: List[Tuple[float, float]],
                            w: int, h: int, inliers: int) -> float:
        """
        Confidence score 0.0→1.0 basato su:
        - Errore medio di riproiezione (pixel)
        - Rapporto inliers / totale punti
        """
        try:
            H_inv = np.linalg.inv(H)
        except np.linalg.LinAlgError:
            return 0.0

        errors = []
        for pp, fp in zip(pixel_pts, field_pts):
            fp_arr = np.array([[[fp[0], fp[1]]]], dtype=np.float32)
            reprojected = cv2.perspectiveTransform(fp_arr, H_inv)
            rx, ry = reprojected[0][0]
            errors.append(np.hypot(pp[0]-rx, pp[1]-ry))

        mean_err = float(np.mean(errors)) if errors else 999.0
        max_dim  = float(max(w, h))

        # Penalità per errore di riproiezione
        err_score = max(0.0, 1.0 - mean_err / (max_dim * 0.06))

        # Bonus per inliers
        inlier_score = inliers / max(len(pixel_pts), 1)

        return float(np.clip(err_score * 0.7 + inlier_score * 0.3, 0.0, 1.0))
