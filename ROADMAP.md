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

### 🔥 Heatmap Live + Timeline (Prelyt Insights)
> Visualizzazione dinamica del movimento squadra nel tempo, con controllo temporale interattivo.

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

### 🔍 Scouting (Prelyt Scout)
- [ ] Database giocatori
- [ ] Report individuali per giocatore
- [ ] Statistiche per singolo giocatore nel tempo

### ☁️ Cloud & Collaborazione (Prelyt Sync)
- [ ] **Backup cloud** del progetto
- [ ] **Condivisione progetto** con altri utenti

### 🔐 Sistema Login e Licenze
- [ ] **Desktop con login online**: installi → crei account → controllo periodico abbonamento
- [ ] **Modalità offline intelligente**: se abbonamento valido, permetti uso offline 15-30 giorni con messaggio "Serve connessione entro X giorni"
- [ ] **Device binding**: legare licenza a max 2 PC
- [ ] **Refresh token automatico**
- [ ] **Blacklist lato server**: poter disattivare utenti
- [ ] **Check anti-manipolazione data di sistema**

---

## 💡 IDEE FUTURE (backlog)

- [ ] Analizzare 10 partite in contemporanea su server cloud
- [ ] Identificazione automatica modulo tattico in tempo reale
- [ ] Analista Virtuale Autonomo: carica video → tutto automatico → relazione + clip pronte

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
