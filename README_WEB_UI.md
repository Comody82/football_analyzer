# Football Analyzer - Web UI

Applicazione desktop per analisi video calcio con interfaccia Web moderna embedded in PyQt5.

## Caratteristiche

### Timeline Eventi Interattiva
- Visualizzazione eventi su timeline con marker colorati
- Click su marker per saltare al timestamp
- Indicatore posizione real-time durante playback

### Controlli Video Avanzati
- **Speed Control**: 0.5x, 1x, 1.5x, 2x, Frame-by-frame
- **Frame Step**: Avanza singolo frame per analisi dettagliata
- **Restart**: Riavvia video dall'inizio
- **Skip**: Salto -5s / +5s customizzabile

### Sistema Clip Professionale
- Workflow Inizio → Fine per creazione clip rapida
- Modifica clip: Aggiorna inizio/fine con posizione corrente
- Save/Cancel con backup automatico
- Gestione lista clip dinamica

### Strumenti Disegno
- **Tool**: Cerchio, Linea, Freccia, Rettangolo, Testo
- **Customizzazione**: Color picker + thickness selector
- **Preview**: Anteprima real-time durante disegno
- **Clear**: Cancella tutti i disegni

## Tecnologie

- **Backend**: Python 3.10+ con PyQt5
- **Frontend**: HTML5 + CSS3 + Vanilla JavaScript
- **Bridge**: QWebEngineView + QWebChannel
- **Video**: OpenCV per playback video
- **Canvas**: HTML Canvas per timeline e drawing

## Requisiti

```bash
pip install PyQt5 PyQtWebEngine opencv-python
```

## Avvio

```bash
python main_web.py
```

## Struttura Progetto

```
football_analyzer/
├── main_web.py          # Entry point
├── backend.py           # QWebChannel bridge
├── config.py            # Configurazione
├── ui/
│   └── opencv_video_widget.py
├── core/
│   ├── events.py        # EventManager
│   ├── clip_manager.py
│   ├── project.py
│   └── statistics.py
└── frontend/
    ├── index.html       # Layout UI
    ├── styles.css       # Design premium
    ├── script.js        # Main logic
    └── drawing.js       # Drawing system
```

## Documentazione

- `COMPLETAMENTO_FINALE.md` - Riepilogo completo progetto
- `PROGRESS.md` - Progress tracker
- `ROADMAP_PARITA.md` - Roadmap implementazione
- `BLOCCO_*_COMPLETATO.md` - Documentazione per blocco

## Workflow Utilizzo

1. **Carica Video**: File → Carica video
2. **Crea Eventi**: Click pulsante evento durante playback
3. **Timeline**: Naviga eventi tramite marker colorati
4. **Crea Clip**: Click "Inizio" → play → Click "Fine"
5. **Modifica Clip**: Click "Modifica" su clip card
6. **Disegna**: Seleziona tool → disegna su video
7. **Esporta**: Salva progetto con eventi e clip

## Features Implementate

✅ Timeline eventi con markers  
✅ Speed control (0.5x-2x + frame step)  
✅ Sistema clip completo (Inizio/Fine/Modifica/Elimina)  
✅ Drawing tools (Circle, Line, Arrow, Rect, Text)  
✅ Color picker + Thickness selector  
✅ Real-time preview  
✅ Responsive layout  

## Parità Funzionale

**100% parità core features** rispetto alla versione Qt Widgets originale.

Features avanzate opzionali non implementate:
- Tool disegno avanzati (curved arrows, pencil)
- Shape 3D effects
- Shape persistence in eventi
- Bulk operations
- Export MP4 highlights

## License

[Inserire licenza]

## Autore

[Inserire autore]
