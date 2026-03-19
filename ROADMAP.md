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
- [ ] Implementare flusso cloud completo: RunPod Serverless Endpoint (Docker image in build)

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
- [ ] Integrazione videocamera consigliata: **Anpviz 4K doppia lente**
- [ ] Analista Virtuale Autonomo: carica video → tutto automatico → relazione + clip pronte

---

## 📌 NOTE BRANDING

- **Nome prodotto:** PRELYT
- **Slogan:** "Analyze. Prevail."
- **Posizionamento:** NON "software di match analysis" MA "Automated Video Intelligence for Football Performance"
- **Stack:** PyQt5 + Python + YOLOX + Cloudflare R2 + RunPod
