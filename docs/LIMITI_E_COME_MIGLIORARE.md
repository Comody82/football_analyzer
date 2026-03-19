# Limiti attuali e come arrivare a risultati ottimali

## Come fanno i software professionali

I sistemi usati in broadcast (es. BroadTrack, PLayerTV, SoccerNet) e in produzione tipicamente:

1. **Modelli addestrati sul calcio**
   - YOLO (o simili) **fine-tunati** su dataset tipo **SoccerNet** (player, referee, ball), non sul COCO generico.
   - La palla viene rilevata con modelli o dataset specifici; il COCO "sports ball" è debole su palloni piccoli/lontani.

2. **Tracking avanzato**
   - **ByteTrack** o **Bot SORT** (non solo IoU + Hungarian) per associare le detection tra frame.
   - Reti di **re-identification** per mantenere lo stesso ID anche dopo occlusioni.

3. **Filtro geometrico**
   - **Maschera del campo** (pitch mask): si tengono solo le detection il cui centro è dentro il poligono del campo, spesso con homography da calibrazione.

4. **Squadre e arbitro**
   - **Colori maglia** (clustering HSV) come noi, ma spesso integrati con **OCR sui numeri di maglia** per identificare i giocatori.
   - Arbitro: a volte un modello separato "referee" o un cluster dedicato.

5. **Contesto**
   - **Multi-camera** in stadio per coprire tutto il campo; noi lavoriamo su un singolo video (spesso una sola telecamera).
   - **Risoluzione e FPS** alti (HD, 25–50 fps); video compressi o bassa risoluzione peggiorano detection e tracking.

---

## Cosa possiamo fare nel nostro progetto (senza cambiare modello)

- **Calibrazione campo**: usare sempre "Calibra campo" e ritagliare al campo per ridurre falsi positivi (tribune) e migliorare coerenza.
- **Soglie di confidence**: abbassare leggermente la soglia di detection giocatori (es. 0.20) aumenta il numero di giocatori tracciati a costo di qualche falso positivo; la palla è già a 0.12.
- **Video di qualità**: risoluzione almeno 720p, buona illuminazione e inquadratura sul campo migliorano molto detection e colore maglia.
- **Ricalcola squadre**: dopo l’analisi, usare "Ricalcola squadre" per ricalcolare il clustering globale e la stabilizzazione per track.

---

## Già introdotto in questo progetto

- **Tracking in stile ByteTrack** (`analysis/player_tracking.py`): due passaggi di associazione (prima detection ad alta confidence ≥0.5, poi a bassa 0.2–0.5 sui track ancora non matchati). Riduce i cambi di ID in occlusioni rispetto al solo IoU+Hungarian.

---

## Passi successivi possibili (richiedono lavoro aggiuntivo)

- **Modello calcio-specifico (SoccerNet)**: addestrare o usare un YOLO fine-tunato su SoccerNet (player/referee/ball) e sostituirlo a YOLOX-s COCO.
- **Palla**: usare un detector di pallone dedicato o un modello addestrato su frame di calcio.
- **Re-ID**: aggiungere una rete di re-identification per mantenere gli ID tra occlusioni e uscite campo.

### Come integrare un modello SoccerNet (passi concreti)

1. **Pesi del modello**: scaricare o addestrare un modello (es. YOLOv8/v5) su SoccerNet Detection (classi: player, referee, ball). Salvare i pesi in `models/` (es. `models/soccernet_player_referee_ball.pt`).
2. **Punto di ingresso**: la detection giocatori è in `analysis/player_detection.py`. La classe `PlayerDetector` e la funzione `run_player_detection()` sono il punto da estendere:
   - opzione A: aggiungere in `analysis/config.py` una variabile (o env `FOOTBALL_ANALYZER_DETECTION_BACKEND=soccernet`); in `player_detection.py`, se il backend è `soccernet`, importare un modulo opzionale (es. `analysis.detection_backends.soccernet`) che espone un detector con la stessa interfaccia di `PlayerDetector` (`.detect(frame) -> List[BoundingBox]`) e che legge le classi player/referee/ball dal modello SoccerNet.
   - opzione B: sostituire l’inizializzazione di `PlayerDetector` con una factory che carica YOLO SoccerNet se i pesi sono presenti in `models/`.
3. **Formato output**: mantenere lo stesso formato di `player_detections.json` (liste di bbox con `x,y,w,h,conf,team`) e, se il modello ha classe “referee”, mapparla a `team=-1` così il resto della pipeline (clustering, overlay) funziona senza modifiche.
4. **Palla**: se il modello SoccerNet include la classe “ball”, si può riusare la stessa inference per generare anche le ball detection (un solo modello invece di due) e adattare `ball_detection.py` per leggere da lì o da un JSON unificato.

Riferimenti: [SoccerNet](https://www.soccernet.org/), [SoccerNet Challenge](https://github.com/SoccerNet/soccernet), eventuali repo della community con YOLO pre-addestrato su SoccerNet.
