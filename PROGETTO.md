# Football Analyzer – Contesto Progetto

## Descrizione
Software desktop ibrido per la **match analysis calcistica**.
- Funziona **in locale** sul PC dell'utente (desktop app)
- Per PC non potenti, l'analisi pesante viene eseguita **in cloud** (RunPod GPU)
- Il video viene caricato su storage cloud, RunPod scarica il link e restituisce i risultati
- Il software è destinato alla **rivendita tramite abbonamento**

## Stack tecnologico
- **Interfaccia:** PyQt5 (desktop app Windows)
- **Backend/logica:** Python
- **Storage cloud:** Cloudflare R2 (account attivo, bucket configurato con accesso pubblico)
- **GPU cloud:** RunPod Serverless (account attivo, billing configurato, endpoint da creare)
- **Modello AI:** YOLOX-S (object detection giocatori, portiere, arbitro, palla)
- **Dataset:** Roboflow Soccer Players (https://universe.roboflow.com/roboflow-universe-projects/soccer-players-ckbru)

## Struttura cartelle principali
```
C:\football_analyzer\       ← progetto principale
    analysis\               ← logica analisi (player_detection.py ecc.)
    api\                    ← API backend (mock_server.py)
    config\
    core\
    data\
    datasets\
        soccer-yolox-dataset\   ← dataset Roboflow (train/valid/test + data.yaml)
    docs\                   ← documentazione fasi YOLOX
    models\                 ← qui andrà il checkpoint addestrato
    training\               ← script di training
    ui\                     ← interfaccia PyQt5
    frontend\

C:\YOLOX\                   ← repo YOLOX clonato separatamente
    datasets\
        soccer\             ← dataset convertito in formato COCO
            annotations\    ← JSON COCO (train/val)
            train2017\
            val2017\
    exps\example\yolox_soccer\
        yolox_soccer_s.py   ← Exp configurato: num_classes=8, dataset soccer, evaluator COCO
```

## Flusso cloud attuale (DA MODIFICARE)
❌ **Flusso attuale (sbagliato):**
`cloud_client.py` invia il file video direttamente nel body della POST (multipart)

✅ **Flusso corretto da implementare:**
1. Software locale comprime/downscala video (720p / 25fps)
2. Upload video su Cloudflare R2
3. Ottieni URL pubblico del video
4. Invia solo l'URL a RunPod (`POST /v1/jobs` con `video_url`)
5. RunPod scarica il video da R2
6. Analisi GPU con YOLOX
7. Restituisce report
8. Software mostra risultati

## Stato avanzamento YOLOX

| Fase | Descrizione | Stato |
|------|-------------|-------|
| Fase 1 | Repo YOLOX clonato in C:\YOLOX, dipendenze installate | ✅ Completata |
| Fase 2 | Dataset convertito YOLO→COCO, collocato in C:\YOLOX\datasets\soccer | ✅ Completata |
| Fase 3 | Exp soccer creato (yolox_soccer_s.py), num_classes=8, evaluator COCO | ✅ Completata |
| Fase 4 | Training su GPU (scaricare yolox_s.pth, lanciare train.py, salvare best_ckpt.pth) | ⏳ DA FARE su RunPod |
| Fase 5 | Integrare checkpoint nell'app (player_detection.py), adattare 8 classi | ⏳ In attesa Fase 4 |
| Fase 6 | Fine-tuning, metriche mAP/precision/recall | ⏳ Futuro |

## Prossimo step concreto
**Fase 4 – Training su RunPod:**
1. Creare endpoint serverless custom su RunPod con ambiente YOLOX
2. Caricare dataset su R2 (o direttamente su RunPod)
3. Scaricare pesi pre-trained `yolox_s.pth`
4. Lanciare: `python tools/train.py -f exps/example/yolox_soccer/yolox_soccer_s.py -d 4 -b 4 -c yolox_s.pth`
5. Salvare `best_ckpt.pth` in `C:\football_analyzer\models\`

## Classi del modello (8 classi)
`Ball, GOAL, Goalie, NED, Ref, USA, football, player`

## Note importanti
- Il PC locale NON ha GPU Nvidia → il training DEVE avvenire su RunPod
- Con bucket R2 pubblico, ogni oggetto ha URL tipo `https://pub-xxxx.r2.dev/nomefile.mp4`
- In futuro passare a Signed URL per sicurezza (rimandato a dopo V1)
- Non inviare mai il file video direttamente nelle API RunPod (timeout/limiti)
