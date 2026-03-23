# PRELYT – Roadmap Funzionalità
> "Analyze. Prevail."
> Automated Video Intelligence for Football Performance

---

## 🏗️ ARCHITETTURA SUITE

| Modulo | Nome | Descrizione |
|--------|------|-------------|
| 🎬 Analysis Core | **Prelyt Core** | Tagging eventi, timeline, match breakdown |
| 🎥 Clip & Video | **Prelyt Clips** | Creazione clip, export, libreria, highlights |
| 📊 Data & Insights | **Prelyt Insights** | Statistiche avanzate, metriche, report |
| 🧠 Tactical Board | **Prelyt Tactics** | Lavagne, schemi, visualizzazione tattica |
| 👥 Scouting | **Prelyt Scout** | Database giocatori, report individuali |
| ☁️ Cloud & Sync | **Prelyt Sync** | Condivisione, collaborazione, backup |

---

## ✅ FUNZIONALITÀ GIÀ PRESENTI

- [x] Player detection con YOLOX-S custom (8 classi: Ball, GOAL, Goalie, NED, Ref, USA, football, player)
- [x] Training YOLOX completato su RunPod GPU (best_ckpt.pth in models/)
- [x] Team classification con KMeans su colori maglia (team 0 / team 1 / non assegnato)
- [x] Tracking giocatori con ID persistenti per frame
- [x] Visualizzazione bounding box colorati per squadra sul video
- [x] Analisi automatica video con progress bar
- [x] Timeline eventi (Gol, Tiro in Porta, Tiro Fuori, Corner, Passaggio, ecc.)
- [x] Creazione clip da eventi taggati
- [x] Genera Highlights automatici
- [x] Strumenti disegno su video (frecce, cerchi, linee, testo)
- [x] Export report
- [x] Salvataggio progetto
- [x] Cloudflare R2 configurato (bucket match-analysis-videos, URL pubblico attivo)
- [x] Flusso cloud corretto: upload R2 → URL → RunPod (cloud_client.py + r2_storage.py)

---

## 🔧 DA COMPLETARE (priorità alta)

### Analisi Automatica (YOLOX)
- [x] Completare Fase 4: Training YOLOX su RunPod
- [x] Integrare checkpoint addestrato in `player_detection.py`
- [x] Adattare 8 classi: Ball, GOAL, Goalie, NED, Ref, USA, football, player
- [x] Test end-to-end su video di prova
- [x] Implementare flusso cloud completo: RunPod Serverless Endpoint (Docker image attiva, test end-to-end superato)

### UI / UX
- [ ] Rifare estetica generale interfaccia
- [ ] Inserire Dashboard con squadre e giocatori
- [ ] Dare errore se si clicca "Fine" senza aver fatto "Inizia clip"

### Impostazioni
- [ ] Versione software
- [ ] Licenza valida fino a…
- [ ] Utente loggato
- [ ] Lingua

---

## 🏗️ PIPELINE COMPLETA (VERSIONE PRO)
> Ordine corretto: prima dati affidabili, poi visualizzazione e output.

```
Video input (qualsiasi camera)
    ↓ [1] Game Segment Detection      → taglia inizio/fine partita, intervallo
    ↓ [2] Preprocessing               → resize, contrasto, luce
    ↓ [3] Detection (YOLOX)           → rileva giocatori e palla (frame wide o tiled)
    ↓ [4] Tracking (ByteTrack)        → ID persistenti e traiettorie
    ↓ [5] Field Calibration           → input utente → homography_matrix
    ↓ [6] Coordinate Mapping          → pixel → metri reali (sblocca statistiche)
    ↓ [7] Tracking Refinement         → interpolazione, filtri fisici, vincoli campo
    ↓ [8] Event Engine                → passaggi, tiri, recuperi, pressing
    ↓ [9] Metrics Engine              → distanza, heatmap, possesso, PPDA
    ↓ [10] Virtual Camera             → crop intelligente + smoothing → video "regia TV"
    ↓ [11] Lavagna Tattica 2D         → pallini su campo in coordinate reali (metri)
    ↓ [12] Report AI + Export         → PDF, CSV, JSON, testo automatico
```

> **Principio chiave:** Virtual Camera e Lavagna 2D sono layer di visualizzazione — vengono DOPO i dati puliti, non prima.

---

## 🚀 FUNZIONALITÀ PIANIFICATE

### 📹 Clip & Video Intelligence (Prelyt Clips)
- [ ] **Clip automatiche**: cliccando "Tiro" salva automaticamente 10 sec precedenti + 5 successivi
- [ ] **Highlights automatici**: AI genera da sola i tagli video dei momenti salienti
- [ ] **Playlist clip**: organizzazione per giocatore, fase difensiva/offensiva, reparto
- [ ] **Freeze Frame automatico**: pausa + disegno frecce su errore tattico + ripresa dopo 3 sec
- [ ] **Zoom intelligente**: zoom automatico sulla zona dell'azione principale (regia TV)
- [ ] **Video tattico automatico**: AI realizza video con frecce e cerchi dinamici sugli errori

### 🎨 Disegni e Visualizzazioni Tattiche
- [ ] **Cerchio tracking giocatori**: cerchio ancorato alle coordinate YOLOX che segue il giocatore
- [ ] **Frecce di movimento dinamiche**: freccia che indica la direzione della corsa
- [ ] **Linee reparto**: unisce difensori/centrocampisti per mostrare se la linea è storta
- [ ] **Evidenziazione spazi**: colora di rosso i giocatori avversari liberi in area
- [ ] **Cono visuale**: triangolo davanti al giocatore per mostrare le linee di passaggio
- [ ] **Overlay HTML5 Canvas**: disegno in tempo reale sopra il video nel WebEngine
- [ ] **Export video con disegni**: OpenCV + FFmpeg per salvare video con grafiche tattiche
- [ ] **Miglioramento frecce in 3D**

### 📊 Statistiche e Report (Prelyt Insights)
- [ ] **Statistiche automatiche** con report stampabile
- [ ] **Riepilogo numerico visivo**: possesso palla, conteggio tiri (specchio/fuori)
- [ ] **Heatmaps**: mappe di calore zone più occupate dai giocatori
- [ ] **Mappa tiri**: punti precisi sul campo da dove sono partite le conclusioni
- [ ] **Misuratore distanze**: linea che mostra distanza tra reparti (es. difesa-centrocampo)
- [ ] **Filtro per periodo**: analizzare solo un intervallo di tempo (es. primi 15 min del 2° tempo)
- [ ] **Ricerca per giocatore**: "Mostrami tutti i passaggi sbagliati del numero 8"

### 🎥 Architettura Triple-Stream — Campo Intero + Zoom Giocatori + Zoom Palla (Prelyt Core)
> Una singola camera 4K wide 180° alimenta tre stream paralleli per tutta la durata della partita. Nessuna camera aggiuntiva necessaria — tutto in software.

```
Frame 4K raw (3840×2160) — per tutta la partita
        │
        ├─── Stream 1: campo intero (ridotto)
        │     • mapping completo squadra in ogni frame
        │     • heatmap, pressing map, formazione, baricentro
        │     • posizioni relative, eventi tattici globali
        │
        ├─── Stream 2: crop per ogni giocatore (zoom)
        │     • crop bbox giocatore → ~720p+ per player
        │     • jersey OCR → numero maglia
        │     • Re-ID embedding → chi è questo giocatore
        │     • tracking preciso movimenti individuali
        │     (tutti i giocatori in parallelo, stesso frame)
        │
        └─── Stream 3: crop palla (zoom)
              • crop bbox palla + margine → alta risoluzione
              • tracking palla pixel-precise
              • traiettoria, velocità, direzione
              • chi è più vicino → possesso preciso
              • predizione posizione prossimo frame (Kalman)
```

> **Perché 4K è fondamentale**: una palla a 8px in 1080p → 16px in 4K → il crop zoomato raggiunge 64px+ con upscaling, sufficiente per tracking preciso e rilevamento traiettoria.
> **Confronto pro**: Hawkeye e Tracab usano 8-12 camere fisiche per ottenere lo stesso risultato. Prelyt lo replica in software da una singola 4K.

- [ ] **Stream 1 — Analisi tattica completa**: processa frame ridotto → YOLO detection + tracking su campo intero
- [ ] **Stream 2 — Analisi individuale giocatori**: per ogni bbox → crop + upscale → OCR jersey + Re-ID embedding
- [ ] **Stream 3 — Tracking palla ad alta precisione**: crop bbox palla + margine → upscale → Kalman Filter
- [ ] **Fusione tre stream**: combina identità (S2) + posizione (S1) + stato palla (S3) → dati completi per frame
- [ ] **Processing parallelo GPU**: tutti e tre gli stream girano in parallelo su RunPod
- [ ] **Output unificato per frame**: `{track_id, player_name, team, x_m, y_m, jersey_num, ball_owner, ball_x, ball_y, ball_speed}`
- [ ] **Requisito hardware**: funziona pienamente con camera 4K — su 1080p Stream 2 e 3 hanno qualità ridotta

---

### 🎬 Player-Centric Clips — Highlights Personalizzati per Giocatore (Prelyt Clips)
> Grazie al Triple-Stream, il sistema sa esattamente chi ha la palla e quando. Questo sblocca clip automatiche centrate su singoli giocatori.

**Esempio**: "Fammi tutti i momenti in cui De Rossi tocca palla, con 5 secondi prima e 5 dopo"

- [ ] **Trigger per tocco palla**: `if player_X near ball → clip [t-5s, t+5s]`
- [ ] **Filtri evento**: tocco palla / passaggio / tiro / contrasto / palla persa / pressing
- [ ] **Doppia modalità clip**: campo intero (contesto tattico) + zoomata sul giocatore (dettaglio tecnico)
- [ ] **Playlist automatica giocatore**: tutti i momenti del giocatore montati in sequenza → video pronto
- [ ] **Report scouting video**: PDF + video highlights → condivisibile con altri club o agenti
- [ ] **Confronto giocatori**: clip affiancate di 2 giocatori nello stesso tipo di azione
- [ ] **UX**: seleziona giocatore → seleziona tipo evento → genera highlights → esporta

---

### 🧠 AI Avanzata (Prelyt Insights + Prelyt Tactics)
- [ ] **Report descrittivo AI**: tasto "Genera Report IA" → LLM scrive relazione tecnica per allenatore
  - Legge dati JSON da YOLOX (posizioni, passaggi, baricentro, palle perse)
  - Invia a API Claude/GPT con prompt specializzato
  - Output: report Markdown/PDF con testo + grafici
- [ ] **Analisi pattern tattici**: riconoscimento modulo reale (4-4-2, 3-5-2, ecc.)
- [ ] **Pitch Control**: mappa di dominanza (quale giocatore arriverebbe prima sulla palla)
- [ ] **Pressing Intensity / PPDA**: velocità con cui i difensori accorciano sull'avversario
- [ ] **Expected Passes (xP)**: difficoltà di ogni passaggio
- [ ] **Pericolosità zona**: valore di "pericolo" per ogni zona del campo in tempo reale
- [ ] **Event Detection automatico**: riconoscimento automatico cross, tiri, contrasti (SlowFast/Video Transformers)
- [ ] **Analisi "cosa non ha funzionato"**: relazione descrittiva completa post-partita

### 🎥 Virtual Camera – Zoom Automatico (Prelyt Clips)
> Livello prodotto: la camera fisica resta fissa a 180°, Prelyt simula una regia TV virtuale.

- [ ] **Focus intelligente**: centro dell'azione = weighted center tra palla + giocatori vicini (NON solo palla)
  - `focus = weighted_center(ball, nearest_players)`
- [ ] **Bounding box azione**: calcola x_min, x_max, y_min, y_max con margine attorno all'azione
- [ ] **Crop intelligente + resize 16:9**: ritaglio del frame e ridimensionamento output
- [ ] **Smoothing movimento camera**: `alpha = 0.9` per evitare scatti bruschi
- [ ] **Speed limit**: limita velocità movimento camera (max_speed = X px/frame) per evitare salti
- [ ] **Zoom dinamico**: zoom out se azione veloce, zoom in se azione statica
- [ ] **Pipeline completa**: Camera → Tracking → Focus intelligente → Bounding box → Smoothing → Speed limit → Output video

---

### 📷 Compatibilità Videocamere – Camera-Agnostic Platform
> Prelyt funziona con qualsiasi video, qualsiasi campo, qualsiasi livello — ma è ottimizzato per camere wide fisse 180°.

- [ ] **Supporto universale**: compatibile con qualsiasi sorgente video (GoPro, videocamere consumer, smartphone)
- [ ] **Ottimizzazione wide fisse 180°**: algoritmi calibrati per panoramiche fisse
- [ ] **Videocamera consigliata ufficiale**: Anpviz 4K Dual Lens Turret Camera 180°
- [ ] **Piano upgrade utente naturale**:
  1. *Entry*: usa la cam che ha già (qualsiasi)
  2. *Pro*: cam consigliata Anpviz 4K wide fissa
  3. *Elite*: cam fissa + cloud RunPod analisi automatica
- [ ] **Comunicazione corretta**: NON "funziona con tutto" → MA "ottimizzato per wide fisse, compatibile con tutto"

---

### 📣 Posizionamento Marketing
> NON vendere "software di match analysis" → VENDERE intelligenza tattica automatica.

- [ ] **Claim principale**: *"Non ti vendiamo l'hardware. Ti vendiamo l'intelligenza."*
- [ ] **Tagline alternativa A**: *"AI Tactical Analysis in Minutes"*
- [ ] **Tagline alternativa B**: *"Turn Any Football Video into Tactical Insights"*
- [ ] **Vantaggio vs Veo**: Veo vende hardware, Prelyt vende software camera-agnostic
- [ ] **Vero vantaggio competitivo**: camera-agnostic platform
- [ ] **Mercato target**: club dilettantistici che hanno già telecamere o GoPro

---

### 🗺️ Field Calibration + Coordinate Mapping (Prelyt Core)
> Trasforma coordinate pixel → metri reali. Sblocca statistiche, heatmap, lavagna 2D precisa e tutto il Metrics Engine.

- [ ] **Field Calibration UI**: utente clicca 4-6 punti noti sul campo (angoli area, centrocampo) → calcola `homography_matrix`
- [ ] **Homography Matrix**: `cv2.findHomography(pixel_points, real_world_points)` → matrice di trasformazione
- [ ] **Coordinate Mapping**: `real_coords = cv2.perspectiveTransform(pixel_coords, H)` → output in metri (0-105 x, 0-68 y)
- [ ] **Output per frame**: ogni detection include `{x_m: 42.3, y_m: 18.2}` oltre alle coordinate pixel
- [ ] **Calibrazione salvata per progetto**: ricalibra una volta sola, usata per tutta la partita
- [ ] **Validazione visiva**: overlay campo reale su frame per verificare correttezza calibrazione
- [ ] **Preset comuni**: campo 11 standard (105×68m), campo 7 (60×40m), campo 5 (40×20m)

---

### 📐 Tracking Refinement (Prelyt Core)
> Pulisce i dati di tracking prima che arrivino a Event Engine e Metrics Engine.

- [ ] **Interpolazione gap**: se giocatore sparisce N frame → interpola posizione tra frame prima e dopo
- [ ] **Vincolo velocità fisica**: velocità max calcio = 10 m/s → `if speed > 10: discard_or_smooth`
- [ ] **Filtro boundary campo**: scarta detection fuori dal rettangolo di gioco reale
- [ ] **Smoothing traiettorie**: filtro Gaussian/Kalman sulle coordinate per eliminare jitter
- [ ] **Confidence scoring**: ogni detection ha score qualità → segnala dati "stimati" nell'interfaccia

---

### 🔒 Robustezza Tracking – Video Sporchi (Priorità Alta)
> I club useranno camere storte, qualità bassa, luce pessima, pioggia, zoom sbagliati. Questo è il problema che decide se il prodotto funziona o fallisce.

**Pipeline robusta completa**: Video → Preprocessing → Detection (YOLO) → Tracking (ByteTrack+memoria) → Filtering → Interpolation → Confidence scoring → Output stabile

- [ ] **Layer 1 – Preprocessing intelligente**:
  - Normalizzazione luce: `cv2.convertScaleAbs(frame, alpha=1.2, beta=10)`
  - Contrasto adattivo CLAHE per giocatori lontani e maglie
  - Denoise leggero per pioggia e compressione video

- [ ] **Layer 2 – Detection stabile (temporal consistency)**:
  - Se detection mancante → usa posizione frame precedente
  - NON eliminare giocatore subito → aspetta 3-5 frame prima di scartarlo

- [ ] **Layer 3 – Tracking robusto (ByteTrack + Kalman Filter)**:
  - Interpolazione posizione se player sparisce: `pos = interpolate(prev_pos, next_pos)`
  - Memoria breve: mantieni player per 10-20 frame anche se non visibile

- [ ] **Layer 4 – Filtri anti-rumore**:
  - Filtro dimensione: scarta bounding box troppo piccoli
  - Filtro posizione: ignora detection fuori dal rettangolo di gioco

- [ ] **Layer 5 – Field Calibration**:
  - Homography per mappare coordinate reali del campo
  - Scarta detection fuori campo: `if x < 0 or x > 105: discard`

- [ ] **Layer 6 – Ball Tracking**:
  - Predizione Kalman se palla mancante: `predizione = kalman.predict()`
  - Vincolo fisico: la palla non teletrasporta, segue traiettorie fisiche

- [ ] **Layer 7 – Confidence System**:
  - Ogni dato ha punteggio qualità (es. `player_confidence = 0.82`)
  - Se confidence bassa → ignora o segnala come "stimato" nell'interfaccia

- [ ] **Layer 8 – Fallback System**:
  - Quando AI fallisce → fallback: centro massa giocatori + zona palla stimata
  - Meglio approssimato che rotto

---

### 🧠 Tracking Avanzato – Sistema che Capisce il Calcio
> Filosofia: NON migliorare con modelli più pesanti → migliorare con **vincoli intelligenti**. Obiettivo: da "AI che vede" a "sistema che capisce il calcio".

**Pipeline PRO**: Detection → Tracking (Kalman) → Gating → Field constraints → Physics constraints → Consistency scoring → Corrected tracking

- [ ] **Motion Model**: usa velocità + direzione → `next_x = x + vx, next_y = y + vy`; se detection manca → continua a stimare posizione
- [ ] **Gating**: accetta detection solo se vicina alla predizione — `if distance(predicted, detected) < threshold: accept` — elimina player che teletrasportano e ID che saltano
- [ ] **Vincoli fisici giocatori**: velocità massima realistica calcio = 8-10 m/s → `if speed > max_speed: discard`; i giocatori non cambiano direzione istantaneamente
- [ ] **Track Consistency Score**: ogni player ha score → `score += continuità, score -= salti`; se score troppo basso → reset ID o correzione
- [ ] **Re-ID semplice V1** (senza deep learning): `if color_similar and position_close: same_player` — usa colore maglia + posizione, sufficiente per V1
- [ ] **Vincoli campo**:
  - Boundary filter: `if x < 0 or x > 105: discard`
  - Zone Logic: difensore non appare improvvisamente in attacco → `if jump_zone_too_large: suspicious`
  - Distanza minima giocatori: `if distance(playerA, playerB) < min_threshold: error`
  - Densità: `if density > threshold: clean_detections()`
  - Logica possesso: `if ball_far_from_all_players: probable_error`
  - Traiettoria palla: non zig-zag random, segue linee fisiche
- [ ] **Insight chiave**: i sistemi pro NON "vedono meglio" → capiscono cosa è **possibile**
- [ ] **Filosofia finale**: accettare il rumore, correggerlo, non eliminarlo

---

### ✂️ Game Segment Detection – Taglio Automatico Video
> Rileva automaticamente inizio/fine 1° tempo, intervallo, inizio/fine 2° tempo — **prima** dell'upload su R2 per risparmiare ~50% costi cloud.

- [ ] **Campionamento leggero**: 1 frame ogni 2 secondi (no analisi frame-by-frame)
- [ ] **Activity Score per frame**: `activity = 0.4*player_score + 0.3*field_score + 0.2*motion_score + 0.1*ball_score`
  - Se `activity > 0.5` → partita attiva; se `≤ 0.5` → pausa/intervallo
- [ ] **Filtraggio falsi positivi**: scarta segmenti < 2 minuti
- [ ] **Output**: `first_half.mp4` + `second_half.mp4`
- [ ] **UX**: timeline attività + slider manuale per correzioni utente
- [ ] **Taglio con FFmpeg** (veloce, senza ricodifica): `ffmpeg -i input.mp4 -ss START -to END -c copy output.mp4`
- [ ] **Precisione stimata**: 85-95% su video amatoriali senza AI pesante
- [ ] **CRUCIALE**: taglio avviene PRIMA dell'upload su R2 → risparmio ~50% costi cloud

---

### 🗺️ Lavagna Tattica 2D Sincronizzata al Video (Prelyt Tactics)
> Visualizzazione tattica in tempo reale: i giocatori si muovono sulla mappa 2D del campo seguendo il minutaggio del video.

- [ ] **Campo stilizzato 2D**: rendering vettoriale SVG/Canvas del campo da calcio (linee bianche su fondo verde) nella stessa pagina del video player
- [ ] **Giocatori come pallini numerati**: ogni track_id = un pallino colorato (colore squadra) con numero sopra
  - Squadra 0 → cerchio rosso/bianco; Squadra 1 → cerchio blu/bianco; Arbitro → cerchio giallo
  - Numero = track_id (o numero maglia se disponibile)
- [ ] **Sincronizzazione al frame**: la posizione dei pallini si aggiorna a ogni frame del video durante la riproduzione
  - Lettura da `player_tracks.json` → `frames[i].detections[j].{x, y, track_id, team}`
  - Mappatura coordinate video → coordinate campo reale (homography o proporzione semplice)
- [ ] **Tempo reale**: i pallini si muovono fluidi seguendo il cursore del video (play, scrubbing, +5s/-5s)
- [ ] **Palla**: pallino bianco più piccolo per la palla (se rilevata)
- [ ] **Layout affiancato**: lavagna tattica accanto (o sotto) al video player senza aprire nuove finestre
- [ ] **Hover info**: passando il mouse su un pallino → mostra `track_id`, `team`, `conf`
- [ ] **Fase 2**: scie di movimento (trail degli ultimi N frame per ogni giocatore)
- [ ] **Fase 3**: esportazione snapshot PNG del campo in un dato momento

---

### 📏 Rilevamento Fuorigioco Automatico (Prelyt Tactics)
> Disegna automaticamente la linea del fuorigioco sulla Lavagna Tattica 2D e identifica i giocatori in posizione irregolare nel frame esatto del passaggio.

**Come funziona la regola (tecnicamente):**
- La linea del fuorigioco = posizione del **secondo ultimo difensore** (penultimo giocatore più arretrato della squadra che difende, portiere incluso)
- Un attaccante è in fuorigioco se, **nel frame del passaggio**, è oltre questa linea rispetto alla porta avversaria
- Serve: `x_m, y_m` di tutti i giocatori + team assignment + frame esatto del passaggio + direzione di gioco

**Prerequisiti tecnici:**
| Componente | Stato |
|---|---|
| `x_m, y_m` in metri | Già presente nel tracking cloud |
| Team assignment (team 0/1) | In lavorazione (team_links) |
| `ball_tracks` | Salvato dal payload cloud |
| Rilevamento frame del passaggio | Richiede Event Engine |
| Direzione di gioco (quale porta attacca chi) | Configurazione manuale una volta per progetto |
| Identificazione portiere | Jersey OCR o flag manuale |

- [ ] **Linea fuorigioco**: linea tratteggiata rossa verticale = posizione del secondo ultimo difensore al frame del passaggio
- [ ] **Giocatori in fuorigioco**: pallini attaccanti oltre la linea colorati in rosso/lampeggiante
- [ ] **Giocatori in gioco**: pallini attaccanti dietro la linea = verde/normale
- [ ] **Attivazione su evento**: la linea appare solo nei frame taggati come "passaggio" (automatico o manuale)
- [ ] **Toggle manuale**: tasto "Verifica fuorigioco" per attivare la visualizzazione sul frame corrente
- [ ] **Export snapshot**: PNG del campo con linea fuorigioco per review o contestazione

**Prerequisiti da sviluppare prima:**
1. Field Calibration + Coordinate Mapping (`x_m`, `y_m` per tutti i giocatori)
2. Team assignment affidabile (quale team difende/attacca)
3. Event Engine: rilevamento frame preciso del passaggio (o marcatura manuale)
4. Configurazione direzione gioco per progetto (una volta sola)

> **Nota**: la linea va applicata al **frame esatto del passaggio** — 1 frame prima o dopo cambia la valutazione.

---

### 🔥 Heatmap Live + Timeline (Prelyt Insights)
> Visualizzazione dinamica del movimento squadra nel tempo, con controllo temporale interattivo.

- [x] **Toggle "📊 Match / 🔴 Live"**: modalità Match = heatmap cumulativa intera partita; modalità Live = finestra scorrevole ±15 secondi aggiornata ogni 400ms
- [ ] **Slider tempo**: seleziona intervallo temporale (es. minuto 20-35) → heatmap si aggiorna in tempo reale
- [ ] **Heatmap squadra**: densità di presenza per zona del campo per ogni squadra
- [ ] **Heatmap individuale**: zoom su singolo giocatore → zone più frequentate
- [ ] **Animazione movimento**: play della heatmap che evolve nel tempo (vedi come la squadra si sposta)
- [ ] **Filtro per fase**: solo fase offensiva / solo fase difensiva / transizioni
- [ ] **Confronto primo/secondo tempo**: heatmap split per vedere differenze tra i due tempi

---

### 🫸 Pressing Intensity Map (Prelyt Insights)
> Mappa visiva di dove e quanto la squadra pressa, basata su densità giocatori vicino alla palla.

- [ ] **Calcolo pressing score per frame**: `pressing = Σ(1/distance_to_ball)` per ogni difensore entro soglia
- [ ] **Mappa densità**: overlay colorato sul campo (rosso = alta intensità pressing, blu = bassa)
- [ ] **PPDA** (Passes Per Defensive Action): metrica standard pressing — passaggi avversari per ogni azione difensiva
- [ ] **Pressing zones**: identifica in quali zone del campo la squadra pressa di più
- [ ] **Timeline pressing**: grafico temporale dell'intensità pressing durante la partita
- [ ] **Confronto squadre**: pressing squadra A vs squadra B nello stesso match

---

### ⚡ Live Analysis — Statistiche Quasi in Tempo Reale (Prelyt Live)
> Trasforma Prelyt da strumento post-partita a strumento decisionale in campo. L'allenatore guarda i dati all'intervallo e cambia tattica basandosi su numeri reali.

**Scenario d'uso principale**: fine primo tempo → allenatore apre tablet/laptop → vede chi sta rendendo di meno, chi ha corso di più, chi ha perso più palle → cambia tattica o sostituisce giocatore con dati alla mano.

- [ ] **Modalità Live**: toggle all'avvio → attiva processing in streaming invece che post-match
- [ ] **Chunking video**: divide il flusso in segmenti da 30-60 secondi → processa e accumula risultati
- [ ] **Statistiche cumulative real-time**: distanza, tocchi, passaggi aggiornati ogni minuto
- [ ] **Dashboard Live Coach**: schermata semplificata per tablet → ranking giocatori per rendimento
- [ ] **Alert automatici**: notifica se giocatore X cala drasticamente → possibile infortunio o stanchezza
- [ ] **Snapshot intervallo**: al 45° genera automaticamente report PDF con statistiche primo tempo
- [ ] **Latenza target**: < 90 secondi dal campo al dato visibile sul tablet dell'allenatore

---

### 🤖 AI Match Summary (Prelyt Insights)
> Non solo numeri — il sistema genera automaticamente un testo narrativo della partita, leggibile da allenatori e analisti senza dover interpretare grafici o tabelle.

- [ ] **Testo narrativo automatico**: a partire da eventi e metriche genera frasi tipo:
  - *"La squadra A ha dominato il possesso nel secondo tempo con il 63%"*
  - *"Il pressing è aumentato significativamente dopo il 60° minuto"*
  - *"Il giocatore #7 ha percorso 11.2 km, il più attivo in campo"*
- [ ] **Sezioni del summary**: Sintesi partita · Possesso · Pressing · Giocatori chiave · Momenti critici
- [ ] **Tono configurabile**: tecnico (per allenatori) o semplificato (per social/comunicazione)
- [ ] **Export**: testo copiabile, PDF, condivisibile direttamente
- [ ] **Integrazione LLM**: usa Claude API per generare il testo dai dati strutturati
- [ ] **Multilingua**: italiano, inglese, spagnolo

---

### 👤 Player Comparison (Prelyt Scout)
> Confronto diretto tra giocatori o tra prestazioni dello stesso giocatore in partite diverse.

- [ ] **Confronto tra giocatori**: seleziona 2 giocatori → tabella comparativa (distanza, velocità, tocchi, zone)
- [ ] **Confronto tra partite**: stesso giocatore in match diversi → trend nel tempo
- [ ] **Radar chart**: grafico a ragno con metriche chiave (velocità, distanza, pressing, tocchi, heatmap)
- [ ] **Ranking giocatori**: ordina per metrica (es. "chi ha corso di più?", "chi ha pressato di più?")
- [ ] **Export scheda giocatore**: PDF individuale con radar + heatmap + statistiche
- [ ] **Storico partite**: accumula dati partita per partita per ogni giocatore

---

### ⚠️ Error Detection AI (Prelyt Core)
> Il sistema segnala automaticamente quando i dati di tracking non sono affidabili, evitando che statistiche errate vengano presentate come veritiere.

- [ ] **Confidence score per detection**: ogni bounding box ha score 0-1 → sotto soglia = "dato stimato"
- [ ] **Segnalazione tracking incerto**: se un giocatore sparisce e riappare con ID diverso → flag `id_switch`
- [ ] **Velocità impossibile**: se giocatore "teletrasporta" (speed > 10 m/s) → flag `teleport_error`
- [ ] **Gap detection**: se giocatore manca per >5 frame → flag `interpolated` (dato stimato, non reale)
- [ ] **Qualità frame**: rileva frame mossi, sovraesposti, parzialmente coperti → abbassa confidence
- [ ] **Report qualità analisi**: al termine dell'analisi mostra score globale (es. "Qualità dati: 87%")
- [ ] **UI warning**: icona ⚠️ accanto a statistiche con dati a bassa affidabilità
- [ ] **Log errori export**: CSV con tutti gli eventi di tracking incerto per debug avanzato

---

### 🧩 Lavagna Tattica Interattiva (Prelyt Tactics)
> Strumento standalone per allenatori: posizionamento manuale dei giocatori sul campo, animazioni di schema, da mostrare ai giocatori prima o dopo la partita. Indipendente dall'analisi video.

- [ ] **Campo 2D interattivo**: campo verde con linee bianche, orientazione verticale o orizzontale selezionabile
- [ ] **Pedine giocatori drag & drop**: pallini colorati con ruolo/numero (POR, DC, TS, CC, AD, ecc.) trascinabili liberamente sul campo
  - Squadra A → colore personalizzabile (default blu)
  - Squadra B → colore personalizzabile (default rosso)
  - Portiere → colore distinto
- [ ] **Ruoli predefiniti**: toolbar con le pedine per ogni ruolo — click per aggiungere al campo
- [ ] **Moduli rapidi**: carica automaticamente formazione 4-4-2, 4-3-3, 3-5-2, ecc. con un click
- [ ] **Strumenti disegno integrati**: frecce di movimento, linee tratteggiate, cerchi zona, testo libero
  - Freccia corsa giocatore
  - Freccia passaggio
  - Zona evidenziata (rettangolo/cerchio colorato semitrasparente)
- [ ] **Animazione schema**: registra sequenza di posizioni → riproduci come animazione fluida per mostrare lo schema in movimento
- [ ] **Salvataggio schemi**: salva e ricarica schemi con nome (es. "Calcio d'angolo sx", "Pressing alto 4-3-3")
- [ ] **Export immagine**: snapshot PNG/JPG della lavagna per invio su WhatsApp/email
- [ ] **Export video animazione**: esporta l'animazione come MP4 per condivisione
- [ ] **Modalità presentazione**: fullscreen per proiettare su TV/schermo nello spogliatoio
- [ ] **Integrazione con analisi**: opzione per caricare sulla lavagna le posizioni reali rilevate dal video a un dato minuto

---

### 📸 Player Enrollment — Registrazione Visiva Giocatore (Prelyt Scout)
> Registra ogni giocatore con foto in maglia (fronte + dorso) al momento della creazione nel registry. Alimenta Jersey OCR e Re-ID senza friction eccessiva e senza problemi GDPR.

- [ ] **Foto fronte + dorso in maglia**: carica o scatta 2 foto per giocatore al momento del setup squadra
- [ ] **Estrazione automatica colore maglia**: HSV histogram dal crop maglia → salvato nell'embedding del giocatore
- [ ] **Lettura numero maglia dalla foto dorso**: OCR in condizioni controllate → molto più affidabile che da video di partita
- [ ] **Corporatura baseline**: altezza/corporatura stimata dalla foto → supporto Re-ID
- [ ] **Privacy**: solo foto maglia (no obbligatorietà viso), consenso esplicito, dati locali — nessun problema GDPR
- [ ] **UX semplice**: nella scheda giocatore, tasto "📷 Registra" → webcam o upload foto
- [ ] **Opzionale**: il sistema funziona anche senza enrollment, ma con enrollment il Re-ID è molto più preciso

---

### 🔢 Jersey Number Recognition — Auto-link Track ID → Giocatore (Prelyt Core)
> Elimina il collegamento manuale track_id → giocatore leggendo automaticamente il numero di maglia dal video.

> ⚡ **Sinergia con Virtual Camera**: OCR applicato sui frame zoomati dalla Virtual Camera → risoluzione 3-4x superiore → numeri leggibili anche a distanza. Costruire questo layer **dopo** Virtual Camera, non prima.

- [ ] **OCR numero maglia per frame**: su ogni crop giocatore zoomato → OCR (PaddleOCR o CRAFT fine-tuned)
- [ ] **Voto per track_id**: ogni track_id accumula i numeri letti → vince il più frequente (es. track_id 5 → jersey #10 nel 78% dei frame)
- [ ] **Match automatico con registry**: jersey #10 rilevato → cerca `jersey_number=10` nella squadra assegnata → collega automaticamente
- [ ] **Confidenza**: mostra il % di certezza del match — sotto soglia chiede conferma manuale
- [ ] **Fallback manuale**: se OCR non riesce → mantieni collegamento manuale

---

### 🧠 Re-ID Cross-Match — Stesso Giocatore in Partite Diverse (Prelyt Scout)
> Il problema reale: analizzare 20 partite della stessa squadra significa 20 volte il collegamento manuale track_id → giocatore. Re-ID lo fa automaticamente dalla seconda partita in poi.

**Il problema**: ogni analisi genera track_id da zero → De Rossi è "track_id 5" in una partita e "track_id 12" in un'altra.

```
Pipeline riconoscimento giocatori (ordine corretto):
Video raw 180°
    ↓ Virtual Camera (zoom intelligente sul giocatore)
    ↓ Frame ad alta risoluzione (~720p+ per giocatore)
    ↓ Jersey OCR → numero maglia
    ↓ Re-ID embedding → impronta visiva
    ↓ Match con registry → nome giocatore
```

- [ ] **Fase 1 — Embedding per giocatore**: dopo il primo collegamento manuale, estrai e salva l'embedding visivo (colore HSV maglia, histogram, feature CNN da frame zoomato)
- [ ] **Fase 2 — Matching automatico**: nella partita successiva, confronta ogni nuovo track_id con gli embedding salvati → se similarità > soglia → collega automaticamente
- [ ] **Fase 3 — Apprendimento continuo**: ogni collegamento confermato migliora l'embedding del giocatore
- [ ] **Gestione cambio maglia**: maglia casa vs trasferta → salva entrambi gli embedding
- [ ] **Fallback**: se similarità < soglia → suggerimento con % ("Probabilmente De Rossi - 87%")
- [ ] **UX**: primo progetto manuale → dalla seconda partita il sistema propone match automatici

**Tecnologia**: ByteTrack/StrongSORT gestisce Re-ID *all'interno* di un video. L'estensione *cross-video* richiede feature extractor leggero (es. OSNet o ResNet18 fine-tuned su SoccerNet) + database embedding per giocatore.

---

### 🔍 Scouting (Prelyt Scout)
- [ ] Database giocatori
- [ ] Report individuali per giocatore
- [ ] Statistiche per singolo giocatore nel tempo

### ☁️ Cloud & Collaborazione (Prelyt Sync)
- [ ] **Backup cloud** del progetto
- [ ] **Condivisione progetto** con altri utenti

---

### 📡 Monitoring Analisi Cloud — Visibilità sullo Stato dei Job (Prelyt Core)
> Quando un utente avvia un'analisi in cloud, deve sapere se sta andando bene o se è bloccata — senza dover controllare RunPod manualmente.

**✅ Già implementato:**
- Timeout automatico in-app: se job in coda > 8 min → avviso giallo; > 10 min → avviso rosso con istruzione chiara
- **Auto-cancel RunPod dopo 10 min**: job cancellato via API (`POST /cancel/{job_id}`) → nessun addebito; dialog mostra pulsante "Chiudi" + QMessageBox con spiegazione chiara

**🔧 Breve termine:**
- [ ] **Delay Time visibile**: mostrare nel dialog quanti minuti il job è in coda (come su RunPod)
- [ ] **Retry automatico**: se job fallisce → riprova automaticamente 1 volta prima di mostrare errore all'utente

**🟡 Medio termine:**
- [ ] **Notifica email su fallimento**: RunPod supporta webhook → quando job FAILED manda email automatica con job_id, user_id, errore
- [ ] **Dashboard admin**: pagina web semplice (solo per sviluppatore) che mostra tutti i job attivi degli utenti in tempo reale — stato, durata, errori
- [ ] **Log centralizzati**: ogni analisi scrive log su server → puoi vedere pattern di errori frequenti

**🔴 Lungo termine (multi-utente):**
- [ ] **Alert automatici**: se job in coda > 5 min → notifica Slack/email
- [ ] **SLA monitoring**: traccia tempo medio analisi per rilevare degradi delle performance RunPod
- [ ] **Status page pubblica**: pagina tipo "status.prelyt.com" che mostra se il servizio è operativo (verde/giallo/rosso)

---

### 🔐 Sistema Login e Licenze
- [ ] **Desktop con login online**: installi → crei account → controllo periodico abbonamento
- [ ] **Modalità offline intelligente**: se abbonamento valido, permetti uso offline 15-30 giorni con messaggio "Serve connessione entro X giorni"
- [ ] **Device binding**: legare licenza a max 2 PC
- [ ] **Refresh token automatico**
- [ ] **Blacklist lato server**: poter disattivare utenti
- [ ] **Check anti-manipolazione data di sistema**

---

### 🗂️ Database Squadre e Giocatori — API-Football Integration (Prelyt Core)
> L'utente non deve inserire rosa e giocatori a mano. Prelyt gestisce un database aggiornato automaticamente due volte l'anno, trasparente per l'utente finale.

**Problema**: inserire manualmente nome, numero maglia e ruolo di 20+ giocatori per ogni squadra è lento e soggetto a errori. L'utente deve poter importare una rosa completa in 2 click.

**Soluzione adottata — architettura a 3 fasi:**

#### Fase 1 — Database pre-caricato nell'app (ora, piano Gratis API-Football)
> Scaricato una volta con la API key di Prelyt, distribuito come file JSON dentro l'app.

- [x] Dialog "🌐 API-Football" in Squadre e Giocatori → cerca squadra → importa rosa completa
- [x] **UI 4 colonne cascading**: Nazione → Lega → Squadra → Rosa/Giocatori (stile Finder)
- [x] **Ricerca per colonna**: campo di ricerca testuale sopra ogni colonna → filtra in tempo reale
- [ ] **Script di generazione DB**: scarica Serie A, B, C, Champions League, Europa League, Lega Pro → salva `teams_db.json`
- [ ] **Ricerca locale**: l'utente cerca "Milan" → risultati istantanei dal JSON locale, senza internet
- [ ] **Fallback manuale**: squadre dilettantistiche non in API-Football → inserimento manuale come ora
- [ ] **Distribuzione con l'app**: `teams_db.json` incluso nel pacchetto installazione

**Costo**: $0 — 100 req/giorno del piano Gratis bastano per generare il DB una volta.

#### Fase 2 — Aggiornamento automatico stagionale (breve termine)
> Il database si aggiorna da solo alle date di chiusura calciomercato, senza intervento manuale.

**Date fisse ogni anno:**
- **1 settembre** — chiusura mercato estivo
- **1 febbraio** — chiusura mercato invernale

```
GitHub Actions (gratis) — schedulato al 1 settembre e 1 febbraio
    ↓ chiama API-Football con API key Prelyt
    ↓ scarica rose aggiornate (Serie A, B, Champions, ecc.)
    ↓ genera nuovo teams_db.json
    ↓ carica su Cloudflare R2 (bucket già attivo)
    ↓ l'app al prossimo avvio controlla versione → scarica silenziosamente
    ↓ aggiornamento trasparente per l'utente
```

- [ ] **Script aggiornamento automatico** (Python): scarica, genera, versiona il JSON
- [ ] **GitHub Actions workflow**: schedulato alle due date di mercato
- [ ] **Check versione all'avvio**: l'app confronta `db_version` locale vs R2 → aggiorna se necessario
- [ ] **Download silenzioso in background**: QThread scarica il nuovo DB senza bloccare l'app

**Costo**: $0 — GitHub Actions gratis, Cloudflare R2 già pagato.

#### Fase 3 — Backend proxy Prelyt + ricerca live globale (quando 10+ abbonati)
> Nessun utente gestisce API key. Prelyt espone il proprio endpoint, tutti i club cercano qualsiasi squadra del mondo in tempo reale.

```
App utente → api.prelyt.com/teams/search?q=Milan
    ↓ backend Prelyt (una sola API key centralizzata)
    ↓ API-Football Mega plan
    ↓ risultati in tempo reale → qualsiasi squadra, qualsiasi lega, qualsiasi paese
```

- [ ] **Endpoint backend**: `GET /teams/search?q={nome}` → proxy verso API-Football
- [ ] **Endpoint giocatori**: `GET /teams/{id}/players?season={anno}` → rosa completa
- [ ] **Cache server-side**: risultati cachati 24h per ridurre req verso API-Football
- [ ] **Rate limiting per utente**: evita abusi sull'endpoint pubblico
- [ ] **Trasferimenti automatici**: al cambio mercato, database aggiornato server-side

**Piano API-Football consigliato per Fase 3:**

| Piano | Costo | Req/giorno | Quando attivarlo |
|---|---|---|---|
| Gratis | $0 | 100 | Ora — genera DB una volta |
| Pro | $19/mese | 7.500 | 5+ abbonati |
| **Mega** | **$39/mese** | **150.000** | **15+ abbonati — servizio completo** |

**Analisi costi Mega plan ($39/mese) a regime:**

| Abbonati Prelyt | Ricavo mensile (€25/club) | Costo API | % sul ricavo |
|---|---|---|---|
| 10 club | €250 | ~€36 | 14% |
| 30 club | €750 | ~€36 | 5% |
| 100 club | €2.500 | ~€36 | 1.5% |

> Da 10 abbonati il costo API è ampiamente coperto. A regime (30+ club) diventa irrilevante rispetto al ricavo.

**Cosa sblocca il piano Mega:**
- 150.000 req/giorno → illimitato per qualsiasi uso realistico
- **Trasferimenti giocatori** → cambio squadra aggiornato automaticamente
- **Formazioni ufficiali** → importa la formazione ufficiale pre-partita con 1 click
- **Storico statistiche giocatori** → alimenta Prelyt Scout con dati reali di carriera

---

### 🎬 Triple-Stream Processing — Architettura Core (Prelyt Core)
> Un singolo frame 4K viene processato su tre livelli in parallelo: campo intero, giocatori individuali, palla. È l'architettura fondamentale che sblocca tutte le feature avanzate.

```
Frame 4K raw (3840×2160)
        │
        ├─── Stream 1: campo intero (ridotto)
        │     • posizioni di tutti i giocatori e palla
        │     • formazione, heatmap, pressing map
        │     • possesso, baricentro squadra
        │     • analisi tattica globale
        │
        ├─── Stream 2: crop per ogni giocatore (bbox zoomato)
        │     • jersey number OCR (numero maglia leggibile ad alta res)
        │     • Re-ID embedding (impronta visiva per cross-match)
        │     • tracking individuale preciso
        │     • clip personalizzate per giocatore
        │
        └─── Stream 3: crop palla (bbox ball + margine)
              • tracking palla ad alta precisione
              • traiettoria, velocità, direzione
              • possesso: chi è più vicino pixel-level
              • rilevamento evento: quando palla lascia giocatore X → passaggio
              • Kalman Filter più accurato su traiettoria reale
```

**Perché lo Stream 3 (palla) è critico:**
- La palla è il dato più importante — tutti gli eventi dipendono da essa (passaggio, tiro, possesso, pressing)
- Nel raw 180° occupa pochissimi pixel → alta probabilità di perderla in motion blur o occlusione
- Con crop zoomato → Kalman Filter molto più accurato → meno "palla persa", più eventi rilevati correttamente
- Rilevamento passaggio migliorato: palla esce dal crop giocatore A → entra nel crop giocatore B → passaggio confermato

- [ ] **Implementare pipeline Triple-Stream** su frame 4K
- [ ] **Parallelizzazione GPU**: i 3 stream processati in parallelo sullo stesso frame
- [ ] **Stream 1**: detection + tracking classico su campo intero ridotto (es. 1280×720)
- [ ] **Stream 2**: crop per ogni bbox giocatore → OCR + Re-ID embedding
- [ ] **Stream 3**: crop bbox palla con margine → upscale → Kalman Filter su serie temporale
- [ ] **Merge risultati**: unifica i 3 stream in un unico output per frame
- [ ] **Requisito hardware**: funziona pienamente con camera 4K — su 1080p Stream 2 e 3 hanno qualità ridotta

> **Nota chiave**: con camera wide 180° 4K, il Virtual Camera zoom (Stream 2) trasforma un giocatore da 20px a 80px+ nel crop — sufficiente per OCR e Re-ID. È questo che rende la camera consigliata strategica, non solo estetica.

---

### 🎥 Clip Personalizzate per Giocatore (Prelyt Clips)
> Dall'integrazione Triple-Stream nasce la possibilità di generare clip automatiche centrate su un singolo giocatore.

- [ ] **Trigger automatico**: ogni volta che track_id X tocca palla → salva clip -5s/+5s
- [ ] **Clip campo intero**: contesto tattico completo (Stream 1)
- [ ] **Clip zoomata sul giocatore**: dettaglio tecnico individuale (Stream 2)
- [ ] **Utente sceglie il tipo**: campo intero / zoomata / entrambe affiancate
- [ ] **Filtri evento**: "solo tiri", "solo passaggi persi", "solo contrasti", "tutti i tocchi"
- [ ] **Export automatico**: cartella per giocatore con tutte le clip della partita
- [ ] **Report scouting video**: PDF + video per giocatore → pronto da mandare ad altri club
- [ ] **Use case allenatore**: "Mostrami tutti i momenti in cui il terzino riceve in profondità"
- [ ] **Use case scouting**: highlight automatico del giocatore da valutare in un'altra squadra

---

### 📱 Prelyt Mobile — App Smartphone e Tablet (Prelyt Mobile)
> Mobile non è una versione ridotta del desktop — è uno strumento diverso con uno scopo diverso: **decisioni rapide e comunicazione immediata in campo**, non analisi approfondita.

**Filosofia**: meno dati, più azione. L'allenatore non ha tempo durante la partita per leggere tabelle — ha bisogno di 3 numeri chiari e un bottone per taggare.

```
                    +-----------------+
                    |  Cloud Prelyt   |   ← sincronizzazione centrale
                    +-----------------+
                     ^       ^       ^
                     |       |       |
          +----------+ +-----+---+ +-+------------+
          | Desktop  | | Tablet  | | Smartphone   |
          | App      | | App     | | App          |
          +----------+ +---------+ +--------------+
          Analisi       Tagging      Report veloci
          approfondita  live         Mini dashboard
          Report pro    Note vocali  Notifiche live
          Post-partita  Clip istant. Da campo
```

**Come funziona il sistema integrato:**
- **Desktop** → analisi AI completa, report approfonditi, editing clip, statistiche avanzate
- **Tablet** → tagging live durante la partita, clip istantanee, lavagna tattica, dashboard KPI
- **Smartphone** → notifiche, report veloci pre-formattati, note vocali, mini dashboard
- **Cloud** → sincronizza tutto in tempo reale, merge automatico se più dispositivi modificano la stessa partita
- **Modalità offline** → mobile funziona senza rete (eventi salvati localmente) → sync automatica al rientro

#### Funzionalità Mobile

- [ ] **Tagging live ultra-rapido**: interfaccia con 6-8 bottoni grandi (Gol, Tiro, Passaggio, Fallo, Corner, Sostituzione) → 1 tap = evento taggato con timestamp preciso
- [ ] **Dashboard KPI sintetica**: 3-4 metriche chiave visibili a colpo d'occhio (possesso %, km percorsi, passaggi riusciti %, eventi) — niente tabelle, solo numeri grandi e colori
- [ ] **Clip immediate**: seleziona evento taggato → genera clip ±5s → mostra ai giocatori sullo schermo del tablet durante l'intervallo
- [ ] **Note vocali → testo automatico**: parli mentre guardi la partita → STT (Speech-to-Text) converte in nota testuale → salvata nel progetto con timestamp
- [ ] **Disegno tattico su clip**: apri clip → disegna linee, frecce, cerchi con dito su touchscreen → salva versione annotata → condividi con staff
- [ ] **Snapshot intervallo automatico**: al 45° → notifica sul tablet → report pre-formattato con KPI primo tempo pronto da mostrare
- [ ] **Report "da campo"**: PDF semplificato generato in 1 tap → formattato per essere letto in fretta (font grande, pochi dati, colori semaforo verde/giallo/rosso)
- [ ] **Sincronizzazione istantanea con desktop**: inizi analisi su tablet → approfondisci dopo sul desktop senza perdere nulla
- [ ] **Merge automatico conflitti**: se desktop e tablet modificano lo stesso evento → sistema propone versione corretta o chiede scelta

#### Stack tecnologico consigliato
- **React Native** (iOS + Android da unico codebase) oppure **Flutter** per performance native
- **Stesso cloud backend** già usato per RunPod/R2 → API REST condivisa
- **Offline-first**: SQLite locale → sync con cloud quando connessione disponibile

---

### 🧠 AI Tactical Text Generator — La Voce dell'Allenatore (Prelyt Insights)
> Non un report generico — un testo tattico scritto nello stile dell'allenatore, basato sui suoi principi di gioco. I dati vengono interpretati secondo la sua filosofia, non quella di un algoritmo generico.

**Differenza da AI Match Summary**: il Summary descrive cosa è successo. Il Tactical Text Generator interpreta cosa è successo *secondo i principi tattici dell'allenatore*. Due allenatori con gli stessi dati ottengono report completamente diversi.

**Differenza chiave:**
- AI Match Summary → *"Il pressing è aumentato nel secondo tempo"* (descrittivo, generico)
- AI Tactical Text Generator → *"La nostra trappola del fuorigioco ha funzionato solo nei primi 20 minuti — dopo il pareggio la linea difensiva si è abbassata perdendo l'aggressività che chiedo"* (interpretativo, con la voce dell'allenatore)

#### Input del sistema
- [ ] **Principi di gioco** (configurati una volta sola dall'allenatore):
  - "Il mio pressing si attiva quando l'avversario riceve con le spalle alla porta"
  - "Voglio ampiezza in fase offensiva, non verticalizziamo mai a caso"
  - "La transizione difensiva è prioritaria: tutti dietro la linea palla entro 3 secondi"
- [ ] **Esempi di stile**: l'allenatore carica 5-10 esempi di sue analisi passate → il modello impara il suo tono e vocabolario
- [ ] **Dati partita**: eventi, tracking, clip video associate agli eventi

#### Logica AI
- [ ] **Interpretazione secondo principi**: non descrive i dati grezzi — li filtra attraverso la filosofia dell'allenatore
- [ ] **Riconoscimento pattern negativi**: identifica automaticamente le deviazioni dai principi
  - *"Nei minuti 55-70 la squadra ha smesso di pressare alto — 6 situazioni in cui il trigger era attivo ma non è scattato il pressing"*
- [ ] **Riconoscimento pattern positivi**: evidenzia quando i principi hanno funzionato con dati a supporto
- [ ] **Struttura modulare principi**: ogni principio è un modulo JSON indipendente → l'allenatore può aggiornarlo senza riscrivere tutto
  ```json
  {
    "pressing": {
      "trigger": "palla_al_terzino",
      "zona": [60, 105],
      "uomini_richiesti": 3,
      "distanza_max_m": 10,
      "descrizione_allenatore": "voglio aggressività immediata, non aspettiamo"
    }
  }
  ```

#### Output
- [ ] **Commenti automatici per singola azione**: ogni evento taggato riceve un commento contestualizzato
- [ ] **Report tattico per partita**: documento completo con sezioni per ogni principio di gioco — cosa ha funzionato, cosa no, dati a supporto
- [ ] **Insight sintetici per lo staff**: versione compressa (1 pagina) con 3 punti di forza e 3 aree di miglioramento
- [ ] **Scheda individuale giocatore**: per ogni giocatore — quanto ha rispettato i compiti tattici assegnati (es. "ha pressato 8/12 volte quando richiesto — 67%")

#### Architettura tecnica
```
Principi di gioco (JSON locale) ──────┐
Esempi stile allenatore ───────────────┤
                                       ↓
Dati partita (eventi+tracking) → [Prelyt AI Engine] → Report personalizzato
Clip video associate ──────────────────┤     (Claude API)
                                       │
Pattern recognition ───────────────────┘
```

- [ ] **Integrazione LLM**: Claude API con prompt personalizzato dai principi dell'allenatore
- [ ] **Privacy totale**: principi di gioco, esempi di stile e output **mai sul cloud** — elaborazione locale o crittografata
- [ ] **Aggiornamento incrementale**: ogni partita analizzata può affinare il profilo stilistico
- [ ] **Multilingua**: italiano, inglese, spagnolo

> **Argomento commerciale**: i principi di gioco di un allenatore sono proprietà intellettuale riservata. Prelyt è l'unico sistema che usa l'AI per personalizzare l'analisi sulla filosofia dell'allenatore mantenendo tutto in locale. *"La tua tattica è tua. L'AI elabora i dati, non i tuoi segreti."*

---

## 💡 IDEE FUTURE (backlog)

- [ ] Analizzare 10 partite in contemporanea su server cloud
- [ ] Identificazione automatica modulo tattico in tempo reale
- [ ] Analista Virtuale Autonomo: carica video → tutto automatico → relazione + clip pronte

---

## 📚 DATASET DI RIFERIMENTO

> **Strategia generale**: ogni dataset serve per una fase specifica. Non scaricare tutto subito — aggiungere solo quando si inizia la fase corrispondente.

### 🟢 Roboflow Football Dataset (IN USO)
- **Uso**: training YOLOX detection (bounding box player, ball, referee) ✅ già fatto
- **Formato**: YOLO pronto, tante immagini annotate
- **Quando usarlo**: detection base — è la fondamenta del sistema

### 🔵 SoccerTrack v2 — Dataset Avanzato
- **Contenuto**: 10 partite universitarie 4K panoramiche (~900 min totali)
- **Annotazioni**:
  - Posizioni giocatori in **metri reali** (non pixel) per ogni frame
  - **Jersey numbers** (0-99) per track_id → direttamente utile per Jersey OCR
  - Team labels (left/right), ruoli (player, goalkeeper, referee)
  - **12 classi eventi**: Pass, Drive, Shot, Header, Cross, ecc. → training Event Engine
  - Track ID persistenti → training Re-ID Cross-Match
  - Formato MOTChallenge per tracking
- **Licenza**: MIT — uso commerciale libero ✅
- **Quando usarlo**:
  - Fase Jersey Number OCR → validare e affinare il modello
  - Fase Event Engine avanzato → training su classi evento reali
  - Fase Re-ID Cross-Match → dataset di embedding per riconoscimento giocatori
  - Fase Field Calibration → coordinate reali per validare homography
- **Stato download**:
  - `raw/` ✅ Scaricato — tracking XML + player CSV + jersey numbers + homography (10 partite)
  - `bas/` ✅ Scaricato — 12 classi eventi per 10 partite
  - `mot/` ⏭ Vuota sul Drive
  - `gsr/` ⏭ Skip (~50GB) — coordinate in metri reali già calibrate. **Strategia**: scaricare 1 sola partita quando si implementa Field Calibration
  - `videos/` ⏭ Skip — video 4K non necessari
- **Limiti**: solo 10 partite, calcio universitario giapponese (stile diverso da europeo), no crop maglia etichettati per OCR

### 🟡 SoccerNet Re-ID — Da scaricare per fase Re-ID
- **Contenuto**: 340.000+ crop di giocatori etichettati per re-identificazione
- **Licenza**: ricerca accademica (verificare uso commerciale prima del download)
- **Quando scaricarlo**: quando si inizia la fase **Re-ID Cross-Match** e **Jersey OCR** avanzato
- **Perché**: SoccerTrack v2 ha pochi esempi per training Re-ID robusto — SoccerNet Re-ID aggiunge scala

### 🟡 SoccerNet-Tracking — Da scaricare per Event Engine robusto
- **Contenuto**: 200+ partite professionistiche con tracking etichettato
- **Nota**: footage broadcast (non wide angle) — diverso dal nostro use case ma utile per volume
- **Quando scaricarlo**: quando si inizia training **Event Engine avanzato** e si vuole più varietà oltre SoccerTrack v2
- **Limite**: camera broadcast ≠ camera wide 180° — usare come supplemento, non sostituto

### 🟡 SportsMOT — Da valutare per tracking generico
- **Contenuto**: 240 clip multi-sport in formato MOT standard (include calcio)
- **Quando valutarlo**: se il tracking con ByteTrack mostra problemi di robustezza — aggiunge varietà di scenari

---

## 📌 NOTE BRANDING

- **Nome prodotto:** PRELYT
- **Slogan:** "Analyze. Prevail."
- **Posizionamento:** NON "software di match analysis" MA "AI Tactical Analysis in Minutes"
- **Claim principale:** "Non ti vendiamo l'hardware. Ti vendiamo l'intelligenza."
- **Tagline alternativa:** "Turn Any Football Video into Tactical Insights"
- **Mercato target:** club dilettantistici che hanno già telecamere o GoPro
- **Vantaggio competitivo:** camera-agnostic platform (vs Veo che vende hardware)
- **Videocamera consigliata:** Anpviz 4K Dual Lens Turret Camera 180°
- **Stack:** PyQt5 + Python + YOLOX + Cloudflare R2 + RunPod

---

## 🔒 PRIVACY BY DESIGN — Argomento Commerciale Chiave

> I principi di gioco di un allenatore sono **proprietà intellettuale riservata**. Prelyt è progettato per non toccarli mai.

### Cosa resta locale (mai sul cloud)
- **Principi di gioco**: il cuore della filosofia tattica dell'allenatore — costruzione dal basso, trigger di pressing, schemi di transizione, ecc.
- **Esempi di stile**: i testi scritti dall'allenatore usati per personalizzare il tono dell'AI
- **Video raw**: il filmato della partita non esce mai dal PC dell'utente
- **Dati giocatori**: nomi, ruoli, biometrie del registry — rimangono in locale

### Cosa va sul cloud (solo per elaborazione)
- Dati aggregati e anonimizzati per l'analisi AI (posizioni normalizzate, conteggi eventi)
- Clip già generate (opzionale, solo se l'utente sceglie di condividere)
- Mai dati identificativi abbinati a strategie tattiche

### Perché è un argomento di vendita concreto
Un allenatore professionista **non caricherà mai** i suoi principi di pressing su un server di terze parti. Con Prelyt può usare tutta la potenza dell'AI senza rischiare che la sua filosofia di gioco finisca in mano a concorrenti, altri club, o venga usata per addestrare modelli condivisi.

**Claim commerciale diretto:**
> *"La tua tattica è tua. L'AI elabora i dati, non i tuoi segreti."*

**Mercato target specifico per questa feature:** staff tecnici semiprofessionisti e professionisti (Serie D, Serie C, Lega Pro) che hanno reale necessità di riservatezza tattica e possono permettersi un abbonamento premium.
