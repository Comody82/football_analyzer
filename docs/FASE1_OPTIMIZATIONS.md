# Fase 1: Ottimizzazioni "Pro" implementate

> 2025-02-25

---

## 1.1 FPS ridotto (10 FPS default)

- **Player detection** e **Ball detection** ora accettano `target_fps=10.0` (default).
- Con video a 25 FPS → `frame_step=3` (1 frame ogni 3) → ~2,5x più veloce.
- Con video a 30 FPS → `frame_step=3` → ~3x più veloce.
- `target_fps=0` → comportamento legacy (1 ogni 2 frame).
- Nei JSON output: `frame_step`, `target_fps`.

---

## 1.2 Field crop (area campo)

- Se esiste `field_calibration.json`, il frame viene ritagliato ai bounds del campo prima della detection.
- Meno pixel → inference più veloce e meno rumore (pubblico, tribune).
- Le coordinate delle detection vengono mappate di nuovo al frame completo.
- Nei JSON output: `crop_bounds: {x0, y0, x1, y1}` se usato.
- Parametro: `calibration_path` (opzionale). L'UI lo passa se la calibrazione esiste.

---

## 1.3 Output temporanei (checkpoint)

- Parametro: `checkpoint_interval` (0 = disabilitato).
- Ogni N frame salva `*_checkpoint_<frame_idx>.json` con i risultati parziali.
- Utile per debug e ripresa in caso di crash.
- L'UI usa `checkpoint_interval=0` (default). Può essere usato da `analysis_engine` (es. 2000).

---

## 1.4 Batch processing

- Non implementato (opzionale, complessità maggiore).
- Può essere valutato in seguito se YOLOX supporta inference batch.

---

## File modificati

- `analysis/player_detection.py` – `target_fps`, `calibration_path`, `checkpoint_interval`, `_apply_field_crop`
- `analysis/ball_detection.py` – idem
- `analysis/field_calibration.py` – `FieldCalibrator.get_field_bounds()`
- `ui/player_detection_dialog.py` – passa `calibration_path`, `target_fps`
- `ui/ball_detection_dialog.py` – idem
