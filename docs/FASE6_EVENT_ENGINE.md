# Fase 6 – Event engine

Motore eventi automatici: possesso, passaggio, recupero, tiro, pressing. Eseguito dopo ball tracking e clustering globale; output in formato schema Step 0.1 (events.automatic).

---

## Step 6.1 – Possesso palla

- Per ogni frame: giocatore **più vicino** alla palla **sotto soglia** (metri) → possesso. Soglia da `event_engine_params`: `possession.max_ball_player_distance_m`.
- Attribuzione team da **player_tracks** (team globale dopo clustering).
- **Output**: segmenti continui `{ start_frame, end_frame, team, track_id }` con durata ≥ `min_possession_time_s` (da config).
- Coordinate in **metri** se calibrazione presente (omografia), altrimenti scala approssimata da dimensioni video/campo.

---

## Step 6.2 – Passaggio

- Da possesso: cambio da giocatore A a giocatore B **stesso team** con **spostamento palla** (frame consecutivi).
- Filtri: distanza minima palla (0.5 m) per considerare passaggio reale.
- **Output**: lista eventi `type: "pass"` con `timestamp_ms`, `team`, `track_id` (origine), `track_id_to` (destinazione).

---

## Step 6.3 – Recupero palla

- **Cambio possesso** in zona **difensiva** (coordinate metri da calibrazione). Zone da config: `events.recovery` (x ∈ [0,17] e [88,105] su campo FIFA).
- **Output**: lista eventi `type: "recovery"` con `timestamp_ms`, `team`, `zone` ("left" | "right").

---

## Step 6.4 – Tiro

- **Velocità palla** (derivata da posizione tra frame consecutivi) oltre soglia `events.shot.min_ball_speed_m_s`.
- **Direzione verso porta** (calibrazione: porte a x=0 e x=105, centro y=34); angolo massimo `max_angle_deg_from_goal`.
- **Output**: lista eventi `type: "shot"` con `timestamp_ms`, `team` (approssimato da direzione).

---

## Step 6.5 – Zona di pressing

- Per ogni frame: **raggio** attorno alla palla (metri) da `events.pressing.radius_around_ball_m`; **conteggio giocatori** per team nel raggio.
- **Output**: evento `type: "pressing"` quando conteggio ≥ `min_players_to_count_pressing` per un team (`zone`: `count_N`).

---

## Step 6.6 – Integrazione nella pipeline

- **Locale**: l’event engine è l’**ultimo step** della pipeline in `analysis_engine.py` (modalità `full`), dopo clustering globale. Scrive **`analysis_output/detections/events_engine.json`** con:
  - `possession_segments`: segmenti possesso
  - `automatic`: array eventi (pass, recovery, shot, pressing) in formato schema Step 0.1
- **Cloud**: stesso modulo e stessi parametri; lo step può essere eseguito nel job dopo ball tracking e clustering; l’output viene incluso nel payload di GET `/v1/jobs/{id}/result` sotto `events.automatic` (e opzionalmente possession per metriche).
- **Formato evento** (allineato a `docs/analysis_result_schema.json`):
  - `type`: "pass" | "recovery" | "shot" | "pressing"
  - `timestamp_ms`, `end_ms` (null), `team`, `track_id`, `track_id_to`, `zone`

Modulo: **`analysis.event_engine`**. Funzioni:
- **`run_event_engine(player_tracks, ball_tracks, fps, calibration_path=None, params=None)`** → dict con `possession_segments` e `automatic`.
- **`run_event_engine_from_project(project_analysis_dir, fps, progress_callback=None)`** → carica tracks e calibrazione, esegue engine, scrive `events_engine.json`; ritorna True/False.

Parametri: **`config/event_engine_params.json`** e **`analysis.event_engine_params`** (Fase 5).
