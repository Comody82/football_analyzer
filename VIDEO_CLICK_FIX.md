# Test Video Click - Istruzioni

## Problema Risolto

Il click sull'area video non veniva intercettato. Ora è stato implementato correttamente.

## Modifiche Implementate

### 1. HTML (`frontend/index.html`)
Aggiunto elemento `videoClickArea`:
```html
<div id="videoClickArea" class="video-click-area"></div>
```

### 2. CSS (`frontend/styles.css`)
Aggiunto stile per area clickable:
```css
.video-click-area {
    position: absolute;
    top: 0; left: 0;
    width: 100%; height: 100%;
    z-index: 5;
    cursor: pointer;
    pointer-events: auto;
}

.video-click-area.drawing-active {
    pointer-events: none; /* Disabilitato quando tool disegno attivo */
}
```

### 3. JavaScript (`frontend/script.js`)
Implementate funzioni:
- `initVideoClickHandler()`: Inizializza event listener
- `handleVideoClick(e)`: Intercetta click, calcola coordinate e timestamp

```javascript
function handleVideoClick(e) {
    const rect = videoClickArea.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const timestamp = backend.getVideoPosition();
    
    console.log(`🎬 Video clicked at (${x}, ${y}) - Timestamp: ${timestamp}ms`);
    backend.onVideoClick(x, y, timestamp);
}
```

### 4. Backend Python (`backend.py`)
Aggiunti metodi:
```python
@pyqtSlot(result=int)
def getVideoPosition():
    # Ritorna posizione corrente video in ms

@pyqtSlot(float, float, int)
def onVideoClick(x, y, timestamp):
    # Gestisce click sull'area video
    print(f"[VIDEO CLICK] x={x}, y={y}, timestamp={timestamp}ms")
```

## Comportamento

### Senza Tool Disegno Attivo
- Click su area video → Log in console con coordinate e timestamp
- Backend riceve notifica del click
- Area click abilitata (z-index: 5, sotto canvas disegno)

### Con Tool Disegno Attivo
- Area click **disabilitata** (`pointer-events: none`)
- Canvas disegno intercetta eventi (z-index: 10)
- Tool disegno funziona normalmente

### Deseleziona Tool Disegno
- **Double-click** sull'area video → Deseleziona tool corrente
- Area click riabilitata
- Cursore torna a `pointer`

## Test Manuale

### Test 1: Click Video Base
1. Avvia applicazione
2. Carica un video
3. Click sull'area video
4. **Verifica Console**: 
   ```
   🎬 Video clicked at (123, 456) - Timestamp: 5000ms
   ```
5. **Verifica Console Python**:
   ```
   [VIDEO CLICK] x=123, y=456, timestamp=5000ms
   ```

### Test 2: Click Durante Playback
1. Play video
2. Lascia riprodurre per qualche secondo
3. Click su video
4. **Verifica**: Timestamp corrisponde al momento del click

### Test 3: Interazione con Drawing Tool
1. Click su tool "Cerchio" (⭕)
2. Click su video → Dovrebbe disegnare cerchio, NON loggare click
3. Double-click su video → Deseleziona tool
4. Click su video → Dovrebbe loggare click

### Test 4: Click su Timeline vs Video
1. Click su timeline eventi → Seek al timestamp
2. Click su area video → Log click con timestamp
3. Verifica che i due comportamenti siano distinti

## Utilizzo Futuro

Il click sul video ora può essere usato per:

### 1. Creazione Rapida Eventi
Implementare in backend:
```python
def onVideoClick(x, y, timestamp):
    # Se evento quick-add attivo:
    self.event_manager.add_event(self.quick_add_event_type, timestamp)
```

### 2. Impostazione Inizio/Fine Clip al Click
```python
def onVideoClick(x, y, timestamp):
    if self.clip_mode == 'setting_start':
        self.temp_clip_start = timestamp
    elif self.clip_mode == 'setting_end':
        self.clipEnd()  # Usa timestamp corrente
```

### 3. Posizionamento Annotations
```python
def onVideoClick(x, y, timestamp):
    if self.annotation_mode_active:
        self.add_annotation(x, y, timestamp, self.annotation_type)
```

### 4. Analisi Tattica
```python
def onVideoClick(x, y, timestamp):
    # Registra posizione giocatore sulla mappa
    self.tactical_data.append({
        'timestamp': timestamp,
        'position': (x, y),
        'player_id': self.selected_player
    })
```

## Problemi Risolti

✅ Click area video non intercettato  
✅ Conflitto con canvas drawing overlay  
✅ Coordinate click non calcolate  
✅ Timestamp non disponibile  
✅ Backend non notificato  

## Note Tecniche

### Z-Index Layers
```
Z-Index 15: Speed menu (dinamico)
Z-Index 10: Drawing canvas (quando tool attivo)
Z-Index 5:  Video click area
Z-Index 0:  Video placeholder/content
```

### Pointer Events Management
- **Tool none**: `videoClickArea` attivo, `drawingCanvas` disabilitato
- **Tool attivo**: `videoClickArea` disabilitato, `drawingCanvas` attivo
- **Double-click**: Deseleziona tool, ripristina stato default

### Cross-Browser Compatibility
Usa `getBoundingClientRect()` per coordinate accurate che funzionano su:
- Chrome/Edge (Chromium)
- Firefox
- Safari

## Status

✅ **IMPLEMENTATO E TESTABILE**

Il click sul video ora funziona correttamente e può essere esteso per tutte le funzionalità richieste dall'utente.
