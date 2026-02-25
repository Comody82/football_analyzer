# Football Analyzer

Software per l'analisi video delle partite di calcio con interfaccia moderna e funzionalità complete.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![PyQt5](https://img.shields.io/badge/GUI-PyQt5-green.svg)

## Funzionalità

### Tagging eventi
- **Eventi predefiniti**: Gol, Tiro in Porta, Tiro Fuori, Calcio d'Angolo, Passaggio
- **Eventi personalizzati**: Crea i tuoi tipi con nome, icona e colore
- Timeline interattiva con marker cliccabili per saltare al momento dell'evento

### Strumenti di disegno sul video
- **Cerchio** – Evidenzia zone o giocatori
- **Freccia** – Indica direzioni e movimenti
- **Rettangolo** – Delimita aree
- **Testo** – Aggiungi annotazioni
- **Cono di luce** – Evidenzia fasi d'azione
- Scelta colore per ogni elemento
- Elementi spostabili e selezionabili

### Clip e highlights
- Ritaglio automatico di clip **prima e dopo** ogni evento (secondi configurabili)
- Salvataggio nella cartella `Highlights/`
- Assemblaggio di tutti i clip in un unico video da mostrare ai giocatori
- Richiede **FFmpeg** installato e nel PATH

### Statistiche
- Gol, Tiri in porta, Tiri fuori per squadra
- Calci d'angolo
- Passaggi (con tag manuale)
- Possesso % (calcolato dai passaggi)
- Distanza percorsa (placeholder per tracking futuro)

## Installazione

```bash
# Clona o scarica il progetto
cd football_analyzer

# Crea ambiente virtuale (consigliato)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Installa dipendenze
pip install -r requirements.txt

# Per creare clip e highlights, installa FFmpeg:
# Windows: https://ffmpeg.org/download.html
# Linux: sudo apt install ffmpeg
# Mac: brew install ffmpeg
```

## Avvio

```bash
python main.py
```

## Struttura progetto

```
football_analyzer/
├── main.py              # Entry point
├── config.py            # Configurazioni
├── requirements.txt
├── core/                # Logica applicativa
│   ├── events.py        # Gestione eventi e tipi
│   ├── project.py       # Progetto e disegni
│   ├── clip_manager.py  # Creazione clip con FFmpeg
│   └── statistics.py    # Calcolo statistiche
├── ui/                  # Interfaccia
│   ├── main_window.py   # Finestra principale
│   ├── theme.py         # Stili e palette
│   └── drawing_overlay.py # Overlay disegno
└── Highlights/          # Cartella clip (creata automaticamente)
```

## Utilizzo

1. **Apri video**: File → Apri Video (o pulsante nella sidebar)
2. **Tagga eventi**: Clicca sui pulsanti (Gol, Tiro in Porta, ecc.) nel momento esatto del video
3. **Disegna**: Seleziona uno strumento (Cerchio, Freccia, ecc.), scegli il colore, disegna sul video
4. **Crea clip**: Vai al tab "Clip", imposta secondi prima/dopo, clicca "Crea clip da tutti gli eventi"
5. **Assembla**: Clicca "Assembla highlights" per unire tutti i clip
6. **Statistiche**: Tab "Statistiche" → Aggiorna per vedere i dati

## Note

- **Distanza percorsa**: Richiederebbe tracking dei giocatori (computer vision). Attualmente disponibile come placeholder per implementazione futura.
- **Passaggi**: Vanno taggati manualmente con l'evento "Passaggio" per le statistiche di possesso.
- **Squadra**: Gli eventi sono di default "casa"; per differenziare le squadre servirà un selettore futuro.
