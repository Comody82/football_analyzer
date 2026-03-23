# DECISIONS — Preferenze e Scelte Architetturali

Questo file documenta le decisioni di design e le preferenze dell'utente per il progetto PRELYT.

---

## UI / UX

- **Lingua**: Tutta l'interfaccia è in italiano. Messaggi, label, bottoni, toast.
- **Toast**: Usa overlay HTML personalizzato (QLabel Qt figlio diretto di video_player) invece di QToast/notify. Motivo: testo bianco visibile su sfondo scuro.
- **No dialog bloccanti**: Le analisi lunghe (preprocessing, cloud, tracking) devono girare in QThread separati con progress dialog non-modal.
- **Conferma prima di sovrascrivere**: Qualsiasi operazione distruttiva (cancella clip, sovrascrivi calibrazione) chiede conferma.

## Architettura

- **Privacy by Design**: I dati tattici (player tracks, heatmap, coordinate) restano **sempre locali**. Non vengono mai inviati al cloud. Solo il video preprocessato va su R2/RunPod.
- **Cloud opzionale**: L'analisi cloud (RunPod) è un'opzione, non un requisito. Tutto deve funzionare anche offline con analisi locale.
- **QThread per operazioni lunghe**: Mai bloccare il main thread. Preprocessing, download, analisi cloud usano QThread + worker separati.
- **Signal-based communication**: Python → JS via `pyqtSignal`. JS → Python via `@pyqtSlot`.

## Analisi

- **Field Calibration dual-mode**: Il dialog calibrazione ha due modalità — "Applica al video corrente" (temporanea) e "Salva come profilo" (permanente in `data/calibrations.json`). La calibrazione migliora la precisione pixel→metri.
- **Game Segment Detection**: FFmpeg concat senza ricodifica per tagliare. Soglia activity score = 0.55×motion + 0.45×field_green.
- **Tracking FPS**: I player tracks vengono campionati a ~3 FPS (non 25) per ridurre dimensione JSON. La tactical board interpola la posizione con `Math.round(posMs/1000 * fps)`.
- **Heatmap grid**: 40×26 celle (rapporto 105×68 metri). Sample ogni 5° frame per performance.

## Dati / Storage

- **Calibrations**: `data/calibrations.json` gestito da `CalibrationRegistry`. Formato: `{name, pts_image, pts_field, H_matrix}`.
- **Teams/Players**: `data/teams_players.json` gestito da `TeamsRepository`. Globale, condiviso tra progetti.
- **Team Links**: `<project_folder>/team_links.json` gestito da `ProjectTeamLinks`. Per-progetto.
- **Events Engine**: `<project_folder>/events_engine.json` — eventi automatici (pass, recovery, shot, pressing).
- **Metrics**: `<project_folder>/metrics.json` — statistiche aggregate (distanza, velocità, etc.).

## Cloud (RunPod + R2)

- **R2**: Bucket `match-analysis-videos`. Upload con presigned URL boto3 (non URL pubblico).
- **RunPod**: Endpoint serverless `uvqmvx8xjh5meg`. Timeout auto-cancel dopo 10 minuti.
- **Docker Hub**: `enzo1982/football-analyzer-runpod:latest`. GitHub Actions auto-build su push a main.
- **Post-processing locale**: Dopo il risultato cloud, il backend calcola coordinate metriche, lancia event engine e genera metrics.json in locale.

## Merge / PR Strategy

- Aprire PR per ogni worktree feature branch. Non committare direttamente su main.
- Fare push + PR prima di chiudere la sessione Claude.
- Ogni sessione Claude usa un worktree separato (es. `claude/stoic-ptolemy`).
