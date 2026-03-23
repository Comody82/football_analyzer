# Fase 8 – Generazione report

Export del risultato analisi in JSON, CSV e PDF; integrazione eventi automatici nella timeline UI.

---

## Step 8.1 – Esportazione JSON

- **Modulo**: `analysis.report`.
- **Funzione**: `build_full_result(project_analysis_dir, source="local", project_id=None, ...)` assembla il risultato completo (schema Step 0.1): tracking, eventi (manual + automatic da events_engine.json), metriche (da metrics.json), calibrazione, parameters_used.
- **Export**: `export_json(project_analysis_dir, output_path)` scrive un unico file JSON conforme allo schema.
- **UI**: pulsante **"Esporta report"** in barra → voce **"Esporta come JSON"** → scelta percorso file → salvataggio.

---

## Step 8.2 – Esportazione CSV

- **Funzione**: `export_csv(project_analysis_dir, output_dir_or_file, include_events=True)`.
- **Tabelle**:
  - **Metriche giocatori**: una riga per giocatore (track_id, team, distance_m, passes, passes_success, touches).
  - **Metriche squadre**: una riga per squadra (team_id, possession_pct, passes_total).
  - **Eventi** (opzionale): una riga per evento (type, timestamp_ms, team, track_id, track_id_to, zone).
- Se `output_dir_or_file` è una cartella: crea `players.csv`, `teams.csv`, `events.csv`. Se è un file .csv: usa il path come prefisso (es. `report_players.csv`).
- **UI**: "Esporta report" → **"Esporta come CSV"** → scelta cartella.

---

## Step 8.3 – PDF tecnico

- **Funzione**: `export_pdf(project_analysis_dir, output_path)`. Richiede **reportlab** (`pip install reportlab`).
- **Contenuto**: riepilogo squadre (possesso %, passaggi totali), tabella sintetica metriche giocatori, timeline eventi automatici (tipo, timestamp, team, zona). Stesso dato di JSON/CSV.
- **UI**: "Esporta report" → **"Esporta come PDF"** → scelta file. Se reportlab non è installato viene mostrato un messaggio.

---

## Step 8.4 – Timeline eventi in UI

- **Dati**: eventi da event engine (Step 6) in formato unico (`events.automatic`): type, timestamp_ms, team, track_id, track_id_to, zone.
- **Caricamento**: in `load_analysis_result(project_dir=...)` e in `load_analysis_result(result_payload=...)` vengono caricati gli eventi automatici e passati al backend con **`backend.setAutomaticEvents(json.dumps(automatic))`**.
- **Backend**: `BackendBridge._automatic_events`; **`setAutomaticEvents(events_json)`** imposta la lista e emette `eventsUpdated`; **`getEvents()`** restituisce eventi manuali + automatici (ogni automatico con id `auto_N`, event_type_id `auto_pass`/`auto_recovery`/etc., description/label leggibili).
- **Timeline**: la barra e la lista eventi (frontend esistente) ricevono tutti gli eventi tramite `getEvents()`; sono ordinati per `timestamp_ms` e cliccabili per **seek** al momento dell’evento (`seekToTimestamp`).
- **Prev/Next evento**: **`goToPrevEvent`** e **`goToNextEvent`** considerano sia eventi manuali sia automatici (`_get_all_events_sorted()`).
- **Overlay video**: opzionale (non implementato in questa fase): icone passaggio/tiro/recupero sul video al timestamp; i dati sono già disponibili per una futura estensione.

---

## Riepilogo

| Componente | Ruolo |
|------------|--------|
| `analysis.report` | build_full_result, export_json, export_csv, export_pdf |
| UI "Esporta report" | Menu JSON / CSV / PDF con dialogo percorso |
| Backend setAutomaticEvents / getEvents | Eventi automatici in timeline e prev/next |
| load_analysis_result | Carica eventi engine da progetto o da payload cloud |
