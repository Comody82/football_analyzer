# Fase 2 – Contratto API (per il cloud)

Il client e il backend si sviluppano rispettando **solo** questo contratto.

- **Specifica OpenAPI/Swagger**: `docs/openapi_v1.yaml` (utilizzabile con Swagger UI, codegen, ecc.). Nessuna chiamata diretta a Redis, Celery o provider esterni; cambiare provider = solo configurazione lato backend.

---

## Step 2.1 – Endpoint e payload

Base URL configurabile (es. `https://api.example.com`). Tutti gli endpoint sono sotto il prefisso **`/v1/`**.

### POST /v1/jobs

Crea un nuovo job di analisi.

**Request**

- **Content-Type**: `application/json` (se si invia `video_url`) oppure `multipart/form-data` (se si carica il file video).
- **Payload (JSON)**:
  ```json
  {
    "video_url": "https://storage.example.com/bucket/video.mp4",
    "options": {
      "mode": "full",
      "target_fps": 10,
      "preprocess": true
    }
  }
  ```
  - **video_url** (string, opzionale): URL pubblico o signed del video su storage. Se assente, il client deve inviare il video in **multipart** (campo `video`).
  - **options** (object, opzionale):
    - **mode** (string): `"full"` | `"player"` | `"ball"`. Default: `"full"`.
    - **target_fps** (number): FPS target per il campionamento (es. 10). Default: 10.
    - **preprocess** (boolean): se `true`, richiede preprocesso video (es. 720p, 25 fps) prima dell’analisi. Default: `false`.

- **Alternativa multipart**: `POST /v1/jobs` con `Content-Type: multipart/form-data`:
  - Campo **video** (file): il file video.
  - Campo **options** (string): JSON stringificato di `options` come sopra (stessi campi).

**Response**

- **201 Created** + body:
  ```json
  {
    "job_id": "uuid-o-id-univoco",
    "status": "pending",
    "message": "Job creato"
  }
  ```
- **400 Bad Request**: parametri mancanti o non validi (es. né `video_url` né file).
- **413 Payload Too Large**: video troppo grande (soglia definita dal backend).

---

### GET /v1/jobs/{id}

Restituisce i dettagli del job (identificativo, stato, eventuale messaggio). Utile per verificare esistenza e stato senza scaricare il result.

**Response**

- **200 OK** + body (stesso schema di status sotto):
  ```json
  {
    "job_id": "uuid",
    "status": "running",
    "progress": 45,
    "message": "Fase 2/6 – Player detection",
    "created_at": "2025-02-25T10:00:00Z",
    "updated_at": "2025-02-25T10:05:00Z"
  }
  ```
- **404 Not Found**: job inesistente.

---

### GET /v1/jobs/{id}/status

Restituisce **solo** lo stato aggiornato del job (per polling).

**Response**

- **200 OK** + body:
  ```json
  {
    "job_id": "uuid",
    "status": "pending | running | completed | failed",
    "progress": 0,
    "message": "stringa opzionale",
    "result_url": null
  }
  ```
  - **status**: `pending` (in coda), `running` (in esecuzione), `completed` (terminato con successo), `failed` (errore).
  - **progress** (integer 0–100): percentuale avanzamento (opzionale; 0 se non disponibile).
  - **message**: messaggio di stato (es. "Fase 2/6 – Player detection") o messaggio di errore se `failed`.
  - **result_url** (string | null): se `status === "completed"`, può contenere l’URL da cui scaricare il result (alternativa a `GET /v1/jobs/{id}/result`); altrimenti `null`.

- **404 Not Found**: job inesistente.

---

### GET /v1/jobs/{id}/result

Restituisce il **risultato** dell’analisi. Disponibile solo quando `status === "completed"`.

**Response**

- **200 OK** + body: oggetto che rispetta lo **schema unico risultato analisi** (Step 0.1), definito in `docs/analysis_result_schema.json`. In sintesi:
  - **version**, **source** (`"cloud"`), **project_id** (opzionale)
  - **calibration**: omografia campo o `null`
  - **parameters_used**: fps, target_fps, preprocess, mode
  - **tracking**: `player_tracks`, `ball_tracks` (stessa struttura dei JSON in `analysis_output/detections/`)
  - **events**: `manual`, `automatic` (event engine)
  - **metrics**: `players`, `teams`
  - **clips**, **heatmaps**

- **202 Accepted** o **404 Not Found**: job non ancora completato o inesistente (il backend può restituire 404 se il job non esiste, 202 se esiste ma non è ancora `completed`; da definire in implementazione; il client può usare `GET /v1/jobs/{id}/status` per distinguere).

---

## Step 2.2 – Versioning

- Tutti gli endpoint hanno prefisso **`/v1/`**.
- In futuro si potrà introdurre **`/v2/`** con nuovi campi o endpoint senza modificare `/v1/`; i client esistenti restano su `/v1/`.

---

## Step 2.3 – Formato job e result stabili

- **Job (creazione)**: stesso set di parametri indipendentemente dal provider GPU/worker:
  - Identificazione video: **video_url** (string) oppure **video** (multipart).
  - **options**: `mode`, `target_fps`, `preprocess` (come sopra). Altri parametri opzionali (es. `calibration_url`) possono essere aggiunti in futuro mantenendo compatibilità.
- **Result**: stesso schema definito in **Step 0.1** (`docs/analysis_result_schema.json`). Il backend mappa l’output dei worker (file locali, output Celery, ecc.) in questo formato unico.

---

## Step 2.4 – Un solo “front door”

- Il **client** chiama **solo** la tua API (base URL configurabile).
- Nessuna chiamata diretta a Redis, Celery o provider di coda/GPU.
- Cambiare provider (es. da Celery a altro worker, da un cloud a un altro) richiede **solo** modifiche di configurazione lato backend; il contratto API e il client restano invariati.

---

## Riepilogo endpoint

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| POST   | /v1/jobs | Crea job (video_url + options, oppure multipart video + options) |
| GET    | /v1/jobs/{id} | Dettaglio job (id, status, progress, message, date) |
| GET    | /v1/jobs/{id}/status | Solo status (per polling) |
| GET    | /v1/jobs/{id}/result | Risultato analisi (schema Step 0.1) |
| GET    | /v1/jobs/events | Stream SSE notifiche (Fase 4); query `job_id` |

Notifiche e fallback polling: **`docs/FASE4_NOTIFICATIONS.md`**.

Schema risultato: **`docs/analysis_result_schema.json`** e **`docs/FASE0_ANALYSIS_RESULT_SCHEMA.md`**.
