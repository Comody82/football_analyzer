# Fase 4: Integrazione processo separato in Qt

> 2025-02-25

---

## Modifiche

- **Nuovo:** `ui/analysis_process_dialog.py` – dialog che lancia `analysis_engine` come processo separato
- **main_web.py:** `show_player_detection`, `show_player_tracking`, `show_ball_detection` usano `AnalysisProcessDialog` invece di QThread

---

## Comportamento

1. L’utente clicca "Player detection", "Player tracking" o "Ball detection"
2. Si apre un dialog **non modale** (l’utente può continuare a usare l’app)
3. Il sistema lancia:
   - **`analysis_engine.exe`** se presente in `dist/analysis_engine/`
   - altrimenti **`python analysis_engine.py`**
4. Ogni 1.5 secondi legge `progress.json` per aggiornare la barra di avanzamento
5. Pulsante **"Interrompi"** per terminare il processo
6. A completamento, carica l’overlay di tracking e chiude il dialog

---

## Parametri passati al motore

- `--video`, `--output`, `--mode` (player/ball/full)
- `--fps 10`, `--checkpoint-interval 2000`
- `--crop` se esiste `field_calibration.json`

---

## Note

- L’exe ha un bug con YOLOX (`yolox.exp.default.yolox_s`). Per usare il motore Python, rinomina o rimuovi la cartella `dist/analysis_engine/` così verrà usato `python analysis_engine.py`.
