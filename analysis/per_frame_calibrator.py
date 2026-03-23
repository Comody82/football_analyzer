"""
Calibratore per-frame per camera TV broadcast.

Gestisce una homography dinamica che si aggiorna automaticamente ad ogni
movimento significativo della camera (pan/tilt/zoom), usando AutoFieldDetector
per ricalcolare la homography senza input manuale.

Architettura:
  PerFrameCalibrator
  ├── AutoFieldDetector   → rileva linee campo da ogni frame
  ├── SceneChangeDetector → rileva movimenti camera
  ├── Cache homography    → {frame_idx: DetectionResult}
  └── Fallback statico    → FieldCalibrator manuale (se auto fallisce)

Modalità:
  "auto"   → solo rilevazione automatica
  "static" → solo calibrazione manuale salvata (comportamento precedente)
  "hybrid" → auto con fallback manuale (RACCOMANDATO per camera TV)
"""
import cv2
import numpy as np
from typing import Optional, Dict, Tuple
import logging

from .auto_field_detector import AutoFieldDetector, DetectionResult
from .field_calibration import FieldCalibrator

logger = logging.getLogger(__name__)


# ── Rilevatore scene change ─────────────────────────────────────────────────
class SceneChangeDetector:
    """
    Rileva movimenti significativi della camera confrontando frame consecutivi.
    Usa frame differencing su immagine ridotta per efficienza.
    """

    def __init__(self, threshold: float = 0.12, downsample: int = 4):
        """
        Args:
            threshold: Differenza media normalizzata che indica un camera move (0.12 = 12%)
            downsample: Fattore di riduzione frame per la comparazione (velocità)
        """
        self.threshold  = threshold
        self.downsample = downsample
        self._prev_gray: Optional[np.ndarray] = None

    def has_changed(self, frame: np.ndarray) -> Tuple[bool, float]:
        """
        Ritorna (changed, diff_score).
        changed=True se la camera si è mossa significativamente.
        """
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (w // self.downsample, h // self.downsample))
        gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray  = cv2.GaussianBlur(gray, (7, 7), 0)

        if self._prev_gray is None or self._prev_gray.shape != gray.shape:
            self._prev_gray = gray
            return True, 1.0

        diff_score = float(np.mean(cv2.absdiff(self._prev_gray, gray))) / 255.0
        self._prev_gray = gray

        return diff_score > self.threshold, diff_score

    def reset(self):
        self._prev_gray = None


# ── Calibratore per-frame ───────────────────────────────────────────────────
class PerFrameCalibrator:
    """
    Gestisce la calibrazione per-frame per camera TV broadcast.

    Uso tipico durante l'analisi di un video broadcast:

        calibrator = PerFrameCalibrator(mode="hybrid")
        calibrator.set_static_calibration(manual_calibrator)  # opzionale

        for frame_idx, frame in enumerate(video_frames):
            H = calibrator.get_homography(frame_idx, frame)
            if H is not None:
                coord_m = calibrator.pixel_to_field(px, py, frame_idx)

    Uso leggero (solo homography senza ricalcolo):

        H = calibrator.get_homography(frame_idx)   # usa cache / ultima valida
    """

    def __init__(self,
                 field_w: float = 105.0,
                 field_h: float = 68.0,
                 mode: str = "hybrid",
                 recalibrate_every: int = 60,
                 scene_change_threshold: float = 0.12):
        """
        Args:
            field_w: Larghezza campo in metri (default 105)
            field_h: Altezza campo in metri (default 68)
            mode: "auto" | "static" | "hybrid"
            recalibrate_every: Ricalibra almeno ogni N frame anche senza scene change
            scene_change_threshold: Sensibilità rilevamento camera move (0.05–0.20)
        """
        self.field_w  = field_w
        self.field_h  = field_h
        self.mode     = mode
        self.recalibrate_every = recalibrate_every

        self._detector        = AutoFieldDetector(field_w, field_h)
        self._scene_detector  = SceneChangeDetector(threshold=scene_change_threshold)
        self._static_cal: Optional[FieldCalibrator] = None

        # Stato runtime
        self._cache: Dict[int, DetectionResult]    = {}
        self._last_valid: Optional[DetectionResult] = None
        self._last_cal_frame: int                   = -9999

        # Statistiche
        self._stats = {
            'frames_processed': 0,
            'auto_success':     0,
            'auto_failed':      0,
            'scene_changes':    0,
        }

    # ── Configurazione ──────────────────────────────────────────────────────
    def set_static_calibration(self, calibrator: FieldCalibrator):
        """Imposta la calibrazione manuale come fallback (modalità hybrid)."""
        self._static_cal = calibrator
        logger.info("PerFrameCalibrator: calibrazione statica impostata come fallback")

    def set_mode(self, mode: str):
        """Cambia modalità: 'auto', 'static', 'hybrid'."""
        assert mode in ("auto", "static", "hybrid"), f"Modalità non valida: {mode}"
        self.mode = mode

    # ── API principale ──────────────────────────────────────────────────────
    def get_homography(self, frame_idx: int,
                       frame: Optional[np.ndarray] = None) -> Optional[np.ndarray]:
        """
        Ritorna la homography migliore per il frame specificato.

        Args:
            frame_idx: Indice del frame (per cache)
            frame: Frame BGR opzionale (necessario per auto-detection)

        Returns:
            Matrice homography 3×3 (np.ndarray) o None se non disponibile
        """
        if self.mode == "static":
            return self._static_homography()

        # Usa cache se disponibile
        if frame_idx in self._cache:
            cached = self._cache[frame_idx]
            if cached.is_valid:
                return cached.homography

        # Senza frame non possiamo ricalcolare
        if frame is None:
            return self._fallback_homography()

        # Decide se ricalcolare
        should_recal = self._should_recalibrate(frame_idx, frame)

        if should_recal:
            self._stats['frames_processed'] += 1
            result = self._detector.detect(frame)
            self._cache[frame_idx] = result

            if result.is_valid:
                self._last_valid       = result
                self._last_cal_frame   = frame_idx
                self._stats['auto_success'] += 1
                logger.debug(f"Frame {frame_idx}: auto-cal OK "
                             f"conf={result.confidence:.2f} ({result.method})")
            else:
                self._stats['auto_failed'] += 1
                logger.debug(f"Frame {frame_idx}: auto-cal fallita – {result.error_msg}")
        else:
            # Copia l'ultima valida nella cache
            if self._last_valid and self._last_valid.is_valid:
                self._cache[frame_idx] = self._last_valid

        # Ritorna il meglio disponibile
        if self._last_valid and self._last_valid.is_valid:
            return self._last_valid.homography

        return self._fallback_homography()

    def pixel_to_field(self, px: float, py: float,
                       frame_idx: int = 0,
                       frame: Optional[np.ndarray] = None) -> Optional[Tuple[float, float]]:
        """
        Trasforma coordinate pixel → coordinate campo (metri).
        Versione per-frame: usa la homography del frame corrispondente.
        """
        H = self.get_homography(frame_idx, frame)
        if H is None:
            return None
        pt  = np.array([[[px, py]]], dtype=np.float32)
        out = cv2.perspectiveTransform(pt, H)
        x_m, y_m = float(out[0][0][0]), float(out[0][0][1])

        # Filtra coordinate fuori campo (con margine 10%)
        if not (-self.field_w*0.1 < x_m < self.field_w*1.1 and
                -self.field_h*0.1 < y_m < self.field_h*1.1):
            return None

        return (x_m, y_m)

    def get_confidence(self, frame_idx: int) -> float:
        """Ritorna il confidence score della calibrazione per il frame dato."""
        if frame_idx in self._cache:
            return self._cache[frame_idx].confidence
        if self._last_valid:
            return self._last_valid.confidence
        if self._static_cal and self._static_cal.is_valid():
            return 0.85  # calibrazione manuale = alta confidenza
        return 0.0

    # ── Statistiche ────────────────────────────────────────────────────────
    def get_stats(self) -> dict:
        """Statistiche sull'elaborazione per-frame."""
        processed = self._stats['frames_processed']
        return {
            'mode':              self.mode,
            'frames_processed':  processed,
            'auto_success':      self._stats['auto_success'],
            'auto_failed':       self._stats['auto_failed'],
            'success_rate':      self._stats['auto_success'] / max(processed, 1),
            'scene_changes':     self._stats['scene_changes'],
            'cached_frames':     len(self._cache),
            'last_confidence':   self._last_valid.confidence if self._last_valid else 0.0,
            'last_method':       self._last_valid.method if self._last_valid else 'none',
            'has_static_cal':    self._static_cal is not None and self._static_cal.is_valid(),
        }

    def reset(self):
        """Resetta lo stato (usa quando carichi un nuovo video)."""
        self._cache.clear()
        self._last_valid     = None
        self._last_cal_frame = -9999
        self._scene_detector.reset()
        self._stats = {k: 0 for k in self._stats}
        logger.info("PerFrameCalibrator: stato resettato")

    # ── Internals ───────────────────────────────────────────────────────────
    def _should_recalibrate(self, frame_idx: int, frame: np.ndarray) -> bool:
        """True se è necessario ricalcolare la homography per questo frame."""
        if self._last_valid is None:
            return True  # prima volta

        frames_since_last = frame_idx - self._last_cal_frame
        if frames_since_last >= self.recalibrate_every:
            return True  # ricalibra periodicamente

        changed, score = self._scene_detector.has_changed(frame)
        if changed:
            self._stats['scene_changes'] += 1
            logger.debug(f"Frame {frame_idx}: scene change rilevato (score={score:.3f})")
            return True

        return False

    def _static_homography(self) -> Optional[np.ndarray]:
        """Homography dalla calibrazione statica manuale."""
        if self._static_cal and self._static_cal.is_valid():
            return self._static_cal._homography
        return None

    def _fallback_homography(self) -> Optional[np.ndarray]:
        """Fallback: ultima auto-calibrazione valida → calibrazione statica → None."""
        if self._last_valid and self._last_valid.is_valid:
            return self._last_valid.homography
        return self._static_homography()


# ── Factory helper ──────────────────────────────────────────────────────────
def create_per_frame_calibrator(
    static_calibrator: Optional[FieldCalibrator] = None,
    field_w: float = 105.0,
    field_h: float = 68.0,
    mode: str = "hybrid",
) -> PerFrameCalibrator:
    """
    Crea e configura un PerFrameCalibrator pronto all'uso.

    Args:
        static_calibrator: Calibratore manuale opzionale (fallback)
        field_w: Larghezza campo metri
        field_h: Altezza campo metri
        mode: "auto" | "static" | "hybrid"
    """
    cal = PerFrameCalibrator(field_w=field_w, field_h=field_h, mode=mode)
    if static_calibrator:
        cal.set_static_calibration(static_calibrator)
    return cal
