# DECISIONS — Preferenze e Scelte Architetturali

Questo file documenta le decisioni di design e le preferenze dell'utente per il progetto PRELYT.

---

## Testing — Regola Obbligatoria

Per ogni modifica implementata, Claude deve verificare nell'ordine:

1. `python -c "import ..."` — sintassi e import corretti
2. Test logica core — verifica che la funzione principale funzioni con dati reali/sintetici
3. `python main_web.py` da `C:\football_analyzer` — app si avvia senza crash

**REGOLA CRITICA**: Claude non deve mai dire "ok, puoi aprire l'app" senza aver completato il punto 3.
L'utente fa solo il test visivo (UI, grafica, comportamento). Errori tecnici, import rotti, crash all'avvio devono essere intercettati da Claude PRIMA della consegna.

**Nota**: il worktree è isolato. Testare sempre da `C:\football_analyzer` (repo principale), non dal worktree.

---

## Workflow Sessioni Claude

> **IMPORTANTE — leggere prima di chiudere ogni sessione**

- Alla fine di ogni sessione (o quando una feature è funzionante), **committare e pushare su GitHub**.
- Tutto ciò che non è su `main` (GitHub) può andare perso al cambio di sessione.
- Comando rapido: dire "committa e pusha" e Claude lo fa prima di chiudere.
- Verificare con `git status` che sia tutto pulito prima di chiudere.

**Perché**: nella sessione gallant-bassi molte feature (heatmap, team links, toast, ecc.) erano state sviluppate ma non committate. Al termine della sessione il worktree è stato perso e tutto il lavoro ha dovuto essere recuperato nella sessione successiva.

---

## UI / UX

- **Lingua**: Tutta l'interfaccia è in italiano. Messaggi, label, bottoni, toast.
- **Toast**: Usa overlay HTML personalizzato (QLabel Qt figlio diretto di video_player) invece di QToast/notify. Motivo: testo bianco visibile su sfondo scuro.
- **No dialog bloccanti**: Le analisi lunghe (preprocessing, cloud, tracking) devono girare in QThread separati con progress dialog non-modal.
- **Conferma prima di sovrascrivere**: Qualsiasi operazione distruttiva (cancella clip, sovrascrivi calibrazione) chiede conferma.
- **Calibrazione — UX**: L'app tenta auto-calibrazione in silenzio all'apertura del progetto. Dialog solo se fallisce. "Calibra manualmente" è opzione avanzata, non default.

---

## Architettura

- **Privacy by Design**: I dati tattici (player tracks, heatmap, coordinate) restano **sempre locali**. Non vengono mai inviati al cloud. Solo il video preprocessato va su R2/RunPod.
- **Cloud opzionale**: L'analisi cloud (RunPod) è un'opzione, non un requisito. Tutto deve funzionare anche offline con analisi locale.
- **QThread per operazioni lunghe**: Mai bloccare il main thread. Preprocessing, download, analisi cloud usano QThread + worker separati.
- **Signal-based communication**: Python → JS via `pyqtSignal`. JS → Python via `@pyqtSlot`.
- **LicenseManager**: Singleton. In modalità DEV (`PRELYT_DEV=1` o file `.dev_mode`) non richiede chiave. In produzione verifica online ogni 24h con grace period 30gg offline. Non blocca mai il main thread (check online in thread daemon).

---

## Analisi

- **Field Calibration — 3 modalità**:
  - *Auto* (`AutoFieldDetector`): rileva linee campo con Hough transform → funziona con campo intero visibile (drone, camera fissa, tribuna alta)
  - *Manuale*: utente clicca 4-6 punti noti → calcola omografia → salvato come profilo in `data/calibrations.json`
  - *Dinamica per-frame* (`PerFrameCalibrator`): omografia diversa per ogni frame → necessaria per video broadcast/VEO zoomati → in sviluppo
- **Game Segment Detection**: FFmpeg concat senza ricodifica per tagliare. Soglia activity score = 0.55×motion + 0.45×field_green.
- **Tracking FPS**: I player tracks vengono campionati a ~3 FPS (non 25) per ridurre dimensione JSON. La tactical board interpola la posizione con `Math.round(posMs/1000 * fps)`.
- **Heatmap grid**: 40×26 celle (rapporto 105×68 metri). Sample ogni 5° frame per performance. Modalità Match (cumulativa) e Live (finestra ±15s, polling 400ms).

---

## Dati / Storage

- **Calibrations**: `data/calibrations.json` gestito da `CalibrationRegistry`. Formato: `{name, pts_image, pts_field, H_matrix}`.
- **Teams/Players**: `data/teams_players.json` gestito da `TeamsRepository`. Globale, condiviso tra progetti.
- **Team Links**: `<project_folder>/team_links.json` gestito da `ProjectTeamLinks`. Per-progetto.
- **Events Engine**: `<project_folder>/events_engine.json` — eventi automatici (pass, recovery, shot, pressing).
- **Metrics**: `<project_folder>/metrics.json` — statistiche aggregate (distanza, velocità, etc.).
- **Licenza**: `%APPDATA%\Prelyt\license.dat` — JSON offuscato (XOR + base64). Contiene chiave, piano, scadenza, device_id, last_online_check, last_seen.

---

## Cloud (RunPod + R2)

- **R2**: Bucket `match-analysis-videos`. Upload con presigned URL boto3 (non URL pubblico).
- **RunPod**: Endpoint serverless `uvqmvx8xjh5meg`. Timeout auto-cancel dopo 10 minuti (`max_elapsed_seconds=600` in `run_poll_loop`).
- **Docker Hub**: `enzo1982/football-analyzer-runpod:latest`. GitHub Actions auto-build su push a main.
- **Post-processing locale**: Dopo il risultato cloud, il backend calcola coordinate metriche, lancia event engine e genera metrics.json in locale.

---

## Licenze

- **Formato chiave**: `PRLT-XXXX-XXXX-XXXX-XXXX`
- **Piani**: `DEV` · `FREE` (no cloud) · `PRO` (tutto) · `ELITE` (tutto + priorità RunPod)
- **DEV mode**: attivato da `PRELYT_DEV=1` (env) oppure file `.dev_mode` nella root del progetto. Non richiede chiave, sempre valido. Da usare durante lo sviluppo.
- **Server** (`api.prelyt.com`): non ancora costruito. Il client è pronto. Quando il server esiste, gestirà attivazione, device binding (max 2 PC), blacklist e piani.

---

## Merge / Commit Strategy

- Ogni sessione Claude usa un worktree separato (es. `claude/stoic-ptolemy`).
- Committare direttamente su `main` dal worktree con `git push` — non è necessaria PR per sessioni di sviluppo normale.
- Aprire PR solo per feature grandi o breaking changes che richiedono review.
- Fare push prima di chiudere ogni sessione — tutto deve essere su GitHub.
