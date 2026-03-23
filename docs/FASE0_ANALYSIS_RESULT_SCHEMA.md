# Fase 0 – Formato risultato analisi e calibrazione

## Step 0.1 – Schema unico risultato analisi

Lo schema è definito in **`docs/analysis_result_schema.json`** (JSON Schema draft-07).

### Contenuto

- **version**, **source** (`local` | `cloud`), **project_id** (opzionale)
- **calibration**: dati omografia (pixel_points, field_points, homography, field_length_m, field_width_m) o `null` se non calibrato
- **parameters_used**: fps, target_fps, preprocess, mode
- **tracking**: `player_tracks` e `ball_tracks` (stessa struttura dei JSON attuali in `analysis_output/detections/`)
- **events**: `manual` (eventi UI) e `automatic` (event engine: possession, pass, recovery, shot, pressing)
- **metrics**: `players` (per track_id: distance_m, heatmap, zones, passes, touches), `teams` (possession_pct, passes_total, pressure_map, recovery_zone_avg)
- **clips**: lista con id, name, start_ms, end_ms, url_or_path
- **heatmaps**: mappe per track_id o squadra (URL/path o griglia)

### Uso

- **Output locale**: la pipeline scrive in `analysis_output/` i file esistenti (player_tracks.json, ball_tracks.json, field_calibration.json). Il client può costruire un oggetto che rispetta questo schema leggendo da cartella progetto.
- **Output cloud**: l’API restituisce un JSON che rispetta lo stesso schema (stessi campi); il client usa un unico percorso di caricamento (da file o da risposta API).
- Validazione opzionale in fase di sviluppo con uno strumento che supporti JSON Schema (es. `jsonschema` in Python).

---

## Step 0.2 – Uso coerente della calibrazione

### Dove sono i dati

- **Calibro campo** (UI) salva in `analysis_output/field_calibration.json`:
  - `pixel_points`, `field_points`, `homography` (matrice 3×3)
- Il modulo **`analysis/field_calibration.py`** espone `FieldCalibrator`: `load(path)`, `pixel_to_field(px, py)`, `field_to_pixel(fx, fy)`, `get_field_bounds(path)`.

### Punto unico per pixel → metri

- **`analysis/homography.py`** (nuovo) è il punto unico da usare per trasformare posizioni in metri:
  - `get_calibrator(calibration_path)` restituisce un `FieldCalibrator` caricato (o `None`).
  - Tutti i moduli che hanno bisogno di coordinate campo (event engine, metriche: distanza, zone, heatmap sul campo) devono usare **solo** questo modulo e **non** aprire/interpretare `field_calibration.json` direttamente.
- Il **crop** per detection (bounds in pixel) continua a usare `FieldCalibrator.get_field_bounds(calibration_path)` come oggi.

### Regole

1. **Metriche in metri** (distanza percorsa, heatmap sul campo, zone in metri): usare `homography.get_calibrator(calibration_path)` e poi `.pixel_to_field(px, py)`. Se `get_calibrator` restituisce `None`, le metriche in metri non sono disponibili (o si restituiscono null/zero).
2. **Eventi che usano zone** (es. recupero in area difensiva): definire le zone in coordinate campo (metri) e usare la stessa omografia per convertire la posizione palla/giocatore da pixel a metri, poi verificare se cade in quella zona.
3. **Nessun nuovo pulsante**: la calibrazione resta quella attuale (Calibro campo); si tratta solo di usare in modo coerente i dati esistenti tramite `analysis/homography.py`.

4. **Cache**: `homography.get_calibrator()` mantiene una cache per path; al salvataggio della calibrazione dalla UI viene chiamato `homography.clear_calibrator_cache(path)` così il prossimo utilizzo ricarica il file.
