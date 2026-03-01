# 🎯 ROADMAP: Parità Funzionale Completa Qt → Web

## Obiettivo
Replicare **esattamente** tutte le funzionalità della versione Qt senza modificare design o UX.

## Blocco 1: Timeline Eventi ✅ IN CORSO

### Analisi Qt
```python
# EventTimelineBar (ui/main_window.py:35-107)
- Barra 80px altezza
- Background track grigio
- Progress bar verde (#00D9A5)
- Position indicator (linea verticale)
- Event markers (cerchi colorati)
- Click → seek al timestamp
- Sincronizzazione real-time
```

### Implementazione Web
```javascript
// Canvas-based timeline
- <canvas> element 80px height
- Mouse click per seek
- Drawing loop per markers
- Event listener per posizione corrente
```

### Task
- [ ] Aggiungere canvas timeline in HTML
- [ ] Implementare rendering markers
- [ ] Click handler per seek
- [ ] Sync con backend eventi
- [ ] Update loop per position indicator

---

## Blocco 2: Controlli Player Avanzati ⏳ PENDING

### Analisi Qt
```python
# Controlli (ui/main_window.py:383-470)
speed_btn → Menu: Frame, 0.5x, 1x, 1.5x, 2x
frame_btn → Step singolo frame
restart_btn → Seek 0 + play
rewind_btn → -5s (customizzabile)
forward_btn → +5s (customizzabile)
time_label → "0:00 / 0:00" aggiornato real-time
```

### Task
- [ ] Speed selector dropdown
- [ ] Frame step button
- [ ] Restart button
- [ ] Rewind/Forward con skip seconds
- [ ] Timer display preciso
- [ ] Backend setPlaybackRate()

---

## Blocco 3: Sistema Clip Completo ✅ COMPLETATO

### Analisi Qt
```python
# Clip workflow (ui/main_window.py:536-544, 1187-1298)
1. User click "Inizio" → salva temp_clip_start
2. User click "Fine" → crea clip {id, start, end, duration, name}
3. Lista clip dinamica con _ClipCardWidget
4. Click card → play clip (loop start→end)
5. "Modifica" → entra editing mode
6. "Aggiorna Inizio/Fine" → modifica timestamp
7. "Salva" → conferma modifiche
8. "Annulla" → ripristina backup
9. "Elimina" → rimuove clip
10. "Crea clip da eventi" → automated clip generation
11. "Assembla highlights" → export MP4
```

### Task
- [x] Backend clipStart() salvare timestamp
- [x] Backend clipEnd() creare clip object
- [x] Frontend render clip cards dinamiche
- [x] Play loop clip singola
- [x] Editing mode UI
- [x] Update start/end timestamps
- [x] Save/Cancel logic
- [x] Delete con confirm
- [ ] Bulk create da eventi
- [ ] Export highlights (ffmpeg)

---

## Blocco 4: Strumenti Disegno ✅ COMPLETATO

### Analisi Qt
```python
# Drawing overlay (ui/drawing_overlay.py)
Tools:
- CIRCLE → MousePress: centro, MouseMove: radius, MouseRelease: conferma
- LINE → Press: start, Move: end preview, Release: conferma
- ARROW → Same as LINE + arrowhead
- HIGHLIGHT_RECT → Semi-transparent rectangle
- TEXT → Click → input dialog
- ZOOM → Click + drag rectangle → zoom area

State management:
- _tool: DrawTool enum
- _drawing: bool
- _current_shape: dict
- _shapes: List[dict]
- _start_pos, _end_pos: QPoint

Colors: draw_color selector
Thickness: line_thickness spinbox
Clear: clear all shapes

Persistence:
- shapes salvate in Event.annotations
- reload on seek
```

### Task
- [x] Canvas overlay sopra video
- [x] Tool selector buttons
- [x] Mouse event handlers (down/move/up)
- [x] Shape preview durante drawing
- [x] Color picker
- [x] Thickness slider
- [x] Shapes rendering (Circle, Line, Arrow, Rectangle, Text)
- [x] Clear all button
- [ ] Save shapes in event annotations (opzionale)
- [ ] Load shapes on seek (opzionale)

---

## Priorità Implementazione

1. **Timeline Eventi** (1 giorno)
   - Fondamentale per navigazione
   - Visualizzazione eventi
   
2. **Controlli Player** (4 ore)
   - Speed control
   - Frame stepping
   - Timer accurate

3. **Sistema Clip** (2 giorni)
   - Core feature dell'app
   - Workflow completo
   - Export

4. **Strumenti Disegno** (3 giorni)
   - Feature più complessa
   - Canvas interaction
   - Shape persistence

---

## Note Tecniche

### Canvas vs HTML Elements
- Timeline → Canvas (performance)
- Drawing overlay → Canvas (precisione pixel)
- UI controls → HTML (accessibilità)

### Backend Extensions Needed
```python
# backend.py additions
@pyqtSlot(float)
def setPlaybackRate(rate)

@pyqtSlot()
def stepFrame()

@pyqtSlot(int)
def updateClipStart(clipId, timestamp)

@pyqtSlot(int)
def updateClipEnd(clipId, timestamp)

@pyqtSlot(result=str)
def getEvents() → JSON

@pyqtSlot(str, str)
def saveDrawing(eventId, shapesJson)

@pyqtSlot(str, result=str)
def loadDrawing(eventId) → JSON
```

### File Structure
```
frontend/
├── index.html (updated with new sections)
├── styles.css (timeline, tools, etc.)
├── script.js (main logic)
├── timeline.js (timeline canvas)
└── drawing.js (drawing canvas overlay)
```

---

## Test Checklist

### Blocco 1
- [ ] Timeline visible
- [ ] Markers rendered
- [ ] Click seek works
- [ ] Position updates real-time

### Blocco 2
- [ ] Speed changes applied
- [ ] Frame step works
- [ ] Restart functional
- [ ] Timer shows correct time

### Blocco 3
- [ ] Inizio/Fine workflow
- [ ] Clip cards render
- [ ] Play clip works
- [ ] Edit/Save/Cancel works
- [ ] Delete works
- [ ] Bulk create works
- [ ] Export works

### Blocco 4
- [ ] All tools functional
- [ ] Shapes draw correctly
- [ ] Color/thickness apply
- [ ] Shapes persist
- [ ] Clear works
