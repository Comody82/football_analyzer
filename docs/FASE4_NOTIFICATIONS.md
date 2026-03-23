# Fase 4 – Notifiche al client (cloud)

Il client riceve aggiornamenti sullo stato del job (completato/fallito) tramite **SSE** con fallback a **polling**. Stesso formato evento/status per entrambi i canali.

---

## Step 4.1 – Scelta canale

- **SSE (Server-Sent Events)**: canale solo server → client; sufficiente per "job completato/fallito" e messaggi di progresso.
- **WebSocket**: non richiesto per questo use case; SSE è più semplice (HTTP long-polling, un solo senso).
- **Scelta**: **GET /v1/jobs/events** (SSE). Il client si sottoscrive dopo aver creato il job; il server invia eventi quando lo stato cambia (e almeno un evento finale `completed` o `failed`).

---

## Step 4.2 – Endpoint notifiche

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| GET | /v1/jobs/events | Stream SSE: eventi di stato per uno o più job. Parametro query **job_id** (obbligatorio per ora). |

- **Query**: `job_id` (string, obbligatorio) – il client passa il `job_id` restituito da `POST /v1/jobs`; il server invia solo eventi per quel job.
- **Header risposta**: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`.
- **Body**: stream di eventi SSE (righe `event:`, `data:`, riga vuota). Ogni `data:` è un JSON conforme al formato sotto.
- **Alternativa futura**: `user_id` o `session_id` in header/query per ricevere eventi di tutti i job dell’utente (opzionale).

---

## Step 4.3 – Formato evento

Payload stabile, **allineato** a `GET /v1/jobs/{id}/status` così la stessa logica UI gestisce notifica e polling:

```json
{
  "job_id": "uuid",
  "status": "pending | running | completed | failed",
  "progress": 0,
  "message": "stringa opzionale",
  "result_url": null
}
```

- **status**: come JobStatus (`pending`, `running`, `completed`, `failed`).
- **progress** (integer 0–100): opzionale.
- **message**: messaggio di stato o errore (se `failed`).
- **result_url** (string | null): se `status === "completed"`, può essere l’URL per scaricare il result; altrimenti `null`. Il client può comunque usare `GET /v1/jobs/{id}/result`.

Quando il client riceve un evento con `status === "completed"` o `status === "failed"`, chiude la connessione SSE e aggiorna l’UI (es. "Analisi pronta" o "Analisi fallita"); se `completed`, scarica il result (GET result o result_url).

---

## Step 4.4 – Client: sottoscrizione + fallback

1. Dopo **POST /v1/jobs** il client ottiene `job_id`.
2. **Sottoscrizione**: apre **GET /v1/jobs/events?job_id={job_id}** (SSE). Ogni evento ricevuto aggiorna la UI (progress, message).
3. All’evento **completed** o **failed**: chiude la connessione SSE, aggiorna UI ("Analisi pronta" / "Analisi fallita"), se completed chiama **GET /v1/jobs/{id}/result** e carica il risultato con `load_analysis_result(result_payload=...)`.
4. **Fallback**: se SSE non disponibile (errore di connessione, 4xx/5xx, timeout) o la connessione cade, il client usa **polling** con **GET /v1/jobs/{id}/status** (es. ogni 5–10 s). Stessa logica: quando `status === "completed"` o `"failed"`, interrompe il polling e procede come sopra.
5. **Qt**: eseguire richieste HTTP e lettura SSE in un **QThread** (o worker) per non bloccare la UI; usare segnali per aggiornare progress e per notificare completamento/errore. Per SSE: `requests.get(..., stream=True)` e parsing righe `data:` in un thread; per polling: `QTimer` nel main thread che invoca il worker che fa GET status.

---

## Step 4.5 – Backend: pubblicare a fine job

- Nel **worker** (es. Celery task) che esegue l’analisi, allo stato **completato** o **fallito**:
  - pubblicare un **evento** su un canale interno (es. **Redis pub/sub**: `PUBLISH job_events:{job_id} '{"job_id":"...","status":"completed",...}'`).
- Un componente **API** (o listener nello stesso processo dell’API):
  - mantiene le connessioni SSE aperte per ogni `job_id` (GET /v1/jobs/events);
  - è sottoscritto a Redis (o equivalente) per i canali `job_events:*` (o un unico canale con payload che include `job_id`);
  - quando riceve un messaggio da Redis per un dato `job_id`, invia l’evento sulla connessione SSE corrispondente (formato evento sopra).
- In questo modo il client riceve la notifica in tempo reale senza dover fare polling; il polling resta solo fallback lato client.

---

## Riepilogo

| Componente | Ruolo |
|------------|--------|
| **GET /v1/jobs/events?job_id=** | Endpoint SSE: stream eventi per un job. |
| **Formato evento** | Stesso schema di GET /v1/jobs/{id}/status (job_id, status, progress, message, result_url). |
| **Client** | Dopo POST /v1/jobs: sottoscrive SSE; fallback a polling GET /v1/jobs/{id}/status ogni 5–10 s. |
| **Backend worker** | A fine job (completed/failed): pubblica evento su Redis (o canale interno); API inoltra su SSE. |

Schema risultato e contratti REST invariati rispetto a Fase 2 (`docs/FASE2_API_CONTRACT.md`, `docs/openapi_v1.yaml`).
