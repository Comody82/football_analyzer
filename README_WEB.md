# Football Analyzer - Web UI

## 🎯 Nuova Architettura

L'interfaccia è stata completamente riscritta con tecnologie web moderne, mantenendo tutto il backend Python invariato.

## 📁 Struttura

```
football_analyzer/
├── main_web.py          # Entry point con QWebEngineView
├── backend.py           # Bridge Python ↔ JavaScript (QWebChannel)
├── frontend/
│   ├── index.html       # UI principale
│   ├── styles.css       # Design SaaS premium
│   └── script.js        # Logica frontend + comunicazione
├── core/                # Backend invariato (clip, eventi, etc.)
├── ui/
│   └── opencv_video_widget.py  # Player video (riutilizzato)
└── config.py
```

## 🚀 Come avviare

```bash
python main_web.py
```

## ✨ Features

### Design Premium SaaS
- Layout moderno stile Linear/Notion
- Animazioni fluide e transizioni
- Glow verde laterale sulle clip in play
- Gradienti e ombre professionali
- Dark theme professionale

### Comunicazione Bidirezionale
- **Python → JavaScript**: Segnali per aggiornare UI
- **JavaScript → Python**: Chiamate a funzioni backend

### Clip Card Moderna
- Border-radius 14px
- Background scuro (#0f1b2e)
- Glow verde laterale con CSS gradient overlay
- Pulsante verde (Riproduci) + grigio (Modifica)
- Hover effects e animazioni

### Responsive & Scalable
- Flexbox layout
- Sidebar 320px
- Content area flessibile
- Scrollbar custom

## 🔌 API Python-JavaScript

### Chiamate JavaScript → Python

```javascript
backend.playClip(clipId)
backend.editClip(clipId)
backend.deleteClip(clipId)
backend.createEvent(eventTypeId)
backend.videoPlay()
backend.videoPause()
backend.openVideo()
backend.clipStart()
backend.clipEnd()
```

### Segnali Python → JavaScript

```python
backend.clipsUpdated.emit(json_string)
backend.statusChanged.emit(status_text)
backend.videoLoaded.emit(path)
```

## 🎨 Personalizzazione CSS

Tutte le variabili sono in `:root` in `frontend/styles.css`:

```css
:root {
    --bg-primary: #0a0e16;
    --bg-card: #0f1b2e;
    --accent-primary: #22c55e;
    --radius-lg: 14px;
    /* ... */
}
```

## 📦 Dipendenze

- PyQt5
- PyQtWebEngine

```bash
pip install PyQt5 PyQtWebEngine opencv-python
```

## 🔄 Migrazione da Qt Widgets

- ✅ Backend completamente preservato
- ✅ Logica clip/eventi invariata
- ✅ Player video riutilizzato
- ✅ Comunicazione via QWebChannel
- ✅ UI completamente nuova in HTML/CSS/JS

## 💡 Prossimi Step

1. Integrare player video nell'UI web
2. Aggiungere statistiche real-time
3. Implementare drag & drop
4. Timeline interattiva con eventi
5. Export highlights

## 🐛 Debug

Console JavaScript: F12 o Ispeziona Elemento
Console Python: Output nel terminale

---

**Stato**: ✅ Funzionante - UI moderna premium pronta per produzione
