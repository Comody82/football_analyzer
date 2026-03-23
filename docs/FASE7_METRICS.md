# Fase 7 – Metriche automatiche

Calcolo metriche per giocatore e per squadra dopo l’event engine. Stesse soglie/parametri (Fase 5) e calibrazione; output nel formato unico (schema Step 0.1).

---

## Step 7.1 – Per giocatore

- **Distanza percorsa** (`distance_m`): traiettoria in pixel → omografia → metri; somma delle distanze tra posizioni consecutive (frame per frame). Senza calibrazione si usa una scala stimata da dimensioni campo/video.
- **Heatmap** (`heatmap_grid`): griglia 2D sul campo in metri (celle da 2 m, campo 105×68 → 52×34 celle); conteggio frame per cella per giocatore.
- **Zone occupate** (`zones_pct`): percentuale tempo per zona:
  - **Terzi** (x): difensivo (0–35 m), centrale (35–70 m), offensivo (70–105 m).
  - **Corridoi** (y): left (0–22.7 m), center (22.7–45.3 m), right (45.3–68 m).
- **Passaggi / passaggi riusciti** (`passes`, `passes_success`): da eventi `type: "pass"`; `passes` = conteggio dove il giocatore è origine (`track_id`); `passes_success` = conteggio dove è destinatario (`track_id_to`) o origine.
- **Tocchi palla** (`touches`): numero di frame in cui il giocatore è in possesso (da `possession_segments`).
- **Output**: una voce per `track_id` in `metrics.players` con `track_id`, `team`, `distance_m`, `heatmap_grid`, `zones_pct`, `passes`, `passes_success`, `touches`.

---

## Step 7.2 – Per squadra

- **Possesso %** (`possession_pct`): da `possession_segments`; somma dei frame con possesso per team / totale frame con possesso × 100.
- **Passaggi totali** (`passes_total`): conteggio eventi passaggio per team.
- **Mappa pressione** (`pressure_map`): aggregazione delle heatmap dei giocatori della squadra (griglia 2D somma conteggi per cella).
- **Zona media recupero** (`recovery_zone_avg`): da eventi recupero; media delle posizioni (approssimazione: centro zona "left" [8.5, 34], "right" [96.5, 34]) in metri; `[x_avg, y_avg]` o null se nessun recupero.
- **Output**: una voce per `team_id` in `metrics.teams` con `team_id`, `possession_pct`, `passes_total`, `pressure_map`, `recovery_zone_avg`.

---

## Step 7.3 – Integrazione

- **Calcolo**: eseguito **dopo** l’event engine; in input: `player_tracks`, `ball_tracks`, output dell’event engine (`possession_segments`, `automatic`), calibrazione e FPS. Stesse soglie/parametri (Fase 5) e stesso modulo calibrazione (omografia).
- **Locale**: step aggiuntivo in **`analysis_engine.py`** (modalità `full`) dopo lo step **event_engine**; scrive **`analysis_output/metrics.json`** con `players` e `teams`.
- **Cloud**: stesso modulo e stessa logica nello stesso job dopo l’event engine; le metriche sono incluse nel payload di GET `/v1/jobs/{id}/result` sotto `metrics`.

Modulo: **`analysis.metrics`**. Funzioni:
- **`compute_metrics(player_tracks, ball_tracks, events_result, calibration_path=None, fps=10.0)`** → `{ "players": [...], "teams": [...] }`.
- **`run_metrics_from_project(project_analysis_dir, fps, progress_callback=None)`** → carica tracks e `events_engine.json`, esegue `compute_metrics`, scrive `metrics.json`; ritorna True/False. Richiede che l’event engine sia già stato eseguito.

La fase **"metrics"** è presente nella pipeline (progress) e nel dialog di analisi (es. Fase 8/8 con preprocesso).
