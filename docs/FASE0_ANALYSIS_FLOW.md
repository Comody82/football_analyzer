# Fase 0: Documentazione flusso analisi automatica

> Creata per la migrazione al modello "processo separato" (analysis_engine).
> Data: 2025-02-25

---

## 1. Pipeline completa

```
[Video originale] 
       │
       ▼
[Video preprocessing] (opzionale)
       │ output: preprocessed.mp4
       ▼
[Player detection] ◄── usa preprocessed se esiste, altrimenti originale
       │ output: player_detections.json
       ▼
[Player tracking] ◄── input: player_detections.json
       │ output: player_tracks.json
       │
[Ball detection] ◄── usa stesso video (preprocessed o originale)
       │ output: ball_detections.json
       ▼
[Ball tracking] ◄── input: ball_detections.json
       │ output: ball_tracks.json
       ▼
[Overlay Qt] carica entrambi per visualizzazione
```

---

## 2. Ordine e dipendenze

| Step | Modulo | Input | Output | Dipendenze |
|------|--------|-------|--------|------------|
| 0 | Video preprocessing | video.mp4 | preprocessed.mp4 | Nessuna |
| 1 | Player detection | video (preprocessed o originale) | player_detections.json | Nessuna |
| 2 | Player tracking | player_detections.json | player_tracks.json | Step 1 |
| 3 | Ball detection | video (preprocessed o originale) | ball_detections.json | Nessuna |
| 4 | Ball tracking | ball_detections.json | ball_tracks.json | Step 3 |

**Note:**
- **Player** e **Ball** sono due pipeline indipendenti: possono essere eseguite in parallelo o in qualsiasi ordine.
- Player tracking **richiede** player detection.
- Ball tracking **richiede** ball detection.
- Ball detection (nel dialog attuale) esegue **subito dopo** ball detection in un unico flusso; non sono dialog separati.

---

## 3. Struttura cartelle

```
<project_base>/analysis/<project_id>/
└── analysis_output/
    ├── preprocessed/
    │   └── preprocessed.mp4          # Video preprocessato (opzionale)
    ├── detections/
    │   ├── player_detections.json    # Output player detection
    │   ├── player_tracks.json        # Output player tracking
    │   ├── ball_detections.json      # Output ball detection
    │   └── ball_tracks.json          # Output ball tracking
    └── field_calibration.json        # Calibrazione campo (opzionale)
```

---

## 4. Scelta video input

- `get_video_for_detection(project_analysis_dir, original_video_path)`:
  - Se esiste `analysis_output/preprocessed/preprocessed.mp4` → usa quello.
  - Altrimenti → usa `original_video_path`.

---

## 5. Funzioni principali e parametri

### 5.1 Video preprocessing
- **Funzione:** `analysis.video_preprocessing.preprocess_video(input_path, output_path, ...)`
- **Parametri:** `max_resolution=(1280,720)`, `max_fps=25`

### 5.2 Player detection
- **Funzione:** `analysis.player_detection.run_player_detection(video_path, output_path, ...)`
- **Parametri:** `conf_thresh=0.5`, `classify_teams=True`
- **Frame sampling attuale:** 1 ogni 2 frame (`frame_idx % 2 == 0`)

### 5.3 Player tracking
- **Funzione:** `analysis.player_tracking.run_player_tracking(detections_path, output_path, ...)`
- **Parametri:** `max_age=30`, `iou_thresh=0.3`

### 5.4 Ball detection
- **Funzione:** `analysis.ball_detection.run_ball_detection(video_path, output_path, ...)`
- **Parametri:** `conf_thresh=0.25`, `frame_step=2` (1 ogni 2 frame)

### 5.5 Ball tracking
- **Funzione:** `analysis.ball_tracking.run_ball_tracking(ball_detections_path, output_path, ...)`
- **Parametri:** `max_age=15`, `iou_thresh=0.2`

---

## 6. Entry point UI attuali

| Azione utente | File | Cosa avvia |
|---------------|------|------------|
| Preprocessing | `ui/video_preprocessing_dialog.py` | `preprocess_video()` in QThread |
| Player detection | `ui/player_detection_dialog.py` | `run_player_detection()` in QThread |
| Player tracking | `ui/player_tracking_dialog.py` | `run_player_tracking()` in QThread |
| Ball detection | `ui/ball_detection_dialog.py` | `run_ball_detection()` + `run_ball_tracking()` in QThread |

Tutti usano **QThread** nello stesso processo Qt, non processi separati.

---

## 7. Formato JSON output (schema base)

### player_detections.json
```json
{
  "frames": [{"frame": 0, "detections": [{"x", "y", "w", "h", "conf", "team"}]}],
  "width": 1920, "height": 1080, "fps": 25.0
}
```

### player_tracks.json
- Stessa struttura ma con `track_id` per ogni detection.

### ball_detections.json
```json
{
  "frames": [{"frame": 0, "detection": {"x", "y", "w", "h", "conf"} | null}],
  "width": 1920, "height": 1080, "fps": 25.0
}
```

### ball_tracks.json
- Stessa struttura ma con `track_id` per la detection.
