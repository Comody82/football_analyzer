# Fase 2: CLI Analysis Engine

> 2025-02-25

---

## File creato

- **`analysis_engine.py`** – Entry point CLI per esecuzione in processo separato

---

## Uso da terminale

```bash
# Analisi completa (player + ball)
python analysis_engine.py --video path/to/video.mp4 --output path/to/project_analysis_dir --mode full

# Solo player detection + tracking
python analysis_engine.py --video video.mp4 --output ./out --mode player

# Solo ball detection + tracking
python analysis_engine.py --video video.mp4 --output ./out --mode ball

# Con field crop (se calibration presente)
python analysis_engine.py --video video.mp4 --output ./out --mode full --crop

# Checkpoint ogni 1000 frame (0 = disabilitato)
python analysis_engine.py --video video.mp4 --output ./out --mode full --checkpoint-interval 1000

# Senza priorità bassa (utile per debug)
python analysis_engine.py --video video.mp4 --output ./out --mode full --no-priority
```

---

## Argomenti

| Argomento | Obbligatorio | Default | Descrizione |
|-----------|--------------|---------|-------------|
| `--video` | Sì | - | Path al video |
| `--output` | Sì | - | Project analysis dir (es. `data/analysis/<project_id>`) |
| `--mode` | No | full | `player`, `ball`, `full` |
| `--fps` | No | 10 | FPS target per sampling |
| `--crop` | No | off | Usa field crop se calibration presente |
| `--checkpoint-interval` | No | 2000 | Salva checkpoint ogni N frame (0 = off) |
| `--no-priority` | No | - | Non impostare priorità bassa |

---

## Output per monitoraggio

Nella cartella `output/analysis_output/`:

- **`progress.json`** – Aggiornato durante l’analisi:
  ```json
  {"phase": "player_detection", "current_frame": 5000, "total_frames": 12000, "pct": 42, "message": "..."}
  ```

- **`finished.json`** – Scritto al termine:
  ```json
  {"success": true, "outputs": ["player_detections.json", "player_tracks.json", ...], "error": ""}
  ```

---

## Codici di uscita

- **0** – Analisi completata
- **1** – Errore (video assente, YOLOX non disponibile, ecc.)

---

## Priorità processo

Se `psutil` è installato e `--no-priority` non è usato:

- **Windows**: `BELOW_NORMAL_PRIORITY_CLASS`
- **Linux/macOS**: `nice(10)`

Così il PC resta utilizzabile durante l’analisi.

---

## Dipendenza aggiunta

- `psutil>=5.9.0` (in `requirements.txt`)
