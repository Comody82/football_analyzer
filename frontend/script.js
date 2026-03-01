/**
 * Football Analyzer - Frontend JavaScript
 * Comunicazione bidirezionale con Python backend via QWebChannel
 */

/**
 * Parse JSON sicuro: accetta sia stringa che oggetto già deserializzato
 */
function safeJsonParse(val) {
    if (val === null || val === undefined) return null;
    if (typeof val === 'object') return val;
    if (typeof val === 'string') {
        try {
            return JSON.parse(val);
        } catch (e) {
            console.warn('JSON.parse error:', e);
            return null;
        }
    }
    return null;
}

/** Assicura che il valore sia un array (evita TypeError forEach). */
function ensureArray(val) {
    return Array.isArray(val) ? val : [];
}

let backend = null;
let timelineCanvas = null;
let timelineCtx = null;
let currentDuration = 0;
let currentPosition = 0;
let eventsData = [];
let eventColors = {};
let eventTypes = {};  // event_type_id → { name, emoji }
let drawingSystem = null; // Drawing system instance
const triggeredEventIds = new Set();  // eventi già messi in pausa, reset su seek indietro
let lastTimeUpdateMs = 0;

// Inizializza comunicazione con Python
new QWebChannel(qt.webChannelTransport, function(channel) {
    backend = channel.objects.backend;
    console.log('✅ Backend connesso');
    
    // Registra listener per aggiornamenti dal backend
    backend.clipsUpdated.connect(onClipsUpdated);
    backend.statusChanged.connect(onStatusChanged);
    backend.eventsUpdated.connect(onEventsUpdated);  // Timeline events
    backend.eventCreated.connect(onEventCreated);    // Evento appena creato → selezione card
    backend.eventTypesUpdated.connect(onEventTypesUpdated);  // Event buttons refresh
    backend.timeUpdated.connect(onTimeUpdated);  // Barra progresso
    
    // Inizializza timeline canvas
    initTimelineCanvas();
    
    // Strumenti disegno: controllano Qt DrawingOverlay tramite backend
    initDrawingTools();

    // Richiedi dati iniziali
    requestInitialData();
    
    // Tab e statistiche nella sidebar destra
    initRightSidebarTabs();
});

/**
 * Richiede dati iniziali dal backend
 */
function requestInitialData() {
    if (!backend) return;
    
    const clipsJson = backend.getClips();
    renderClips(ensureArray(safeJsonParse(clipsJson)));
    
    const eventsJson = backend.getEventTypes();
    const events = ensureArray(safeJsonParse(eventsJson));
    if (events.length > 0) {
        renderEventButtons(events);
        events.forEach(evt => {
            eventColors[evt.id] = evt.color;
            eventTypes[evt.id] = { name: evt.name, emoji: evt.emoji || '' };
        });
    }
    
    const eventsDataJson = backend.getEvents();
    const eventsData = ensureArray(safeJsonParse(eventsDataJson));
    updateTimelineEvents(eventsData);
    renderEventList(eventsData);
    
    const timeJson = backend.getCurrentTime();
    const time = safeJsonParse(timeJson);
    if (time && (typeof time.duration === 'number' && time.duration > 0 || typeof time.current === 'number')) {
        updateTimeline(time);
    }
}

/**
 * Callback: Aggiornamento clip dal backend
 */
function onClipsUpdated(clipsJson) {
    const clips = ensureArray(safeJsonParse(clipsJson));
    renderClips(clips);
}

/**
 * Callback: Cambio stato dell'app
 */
function onStatusChanged(status) {
    const statusText = document.querySelector('.status-text');
    if (statusText) {
        statusText.textContent = status;
    }
}

/**
 * Callback: Aggiornamento eventi (timeline + lista)
 */
function onEventsUpdated(eventsJson) {
    const events = ensureArray(safeJsonParse(eventsJson));
    updateTimelineEvents(events);
    renderEventList(events);
}

/**
 * Callback: Aggiornamento tipi evento (pulsanti)
 */
function onEventTypesUpdated(typesJson) {
    const types = ensureArray(safeJsonParse(typesJson));
    if (types.length > 0) {
        renderEventButtons(types);
        types.forEach(evt => {
            eventColors[evt.id] = evt.color;
            eventTypes[evt.id] = { name: evt.name, emoji: evt.emoji || '' };
        });
    }
}

/**
 * Callback: Aggiornamento tempo (barra progresso)
 */
function onTimeUpdated(timeJson) {
    const time = safeJsonParse(timeJson);
    if (time) {
        updateTimeline(time);
        checkEvents(time.current);
    }
}

/**
 * Controlla se il video ha attraversato un evento durante la riproduzione e mette in pausa.
 * La pausa si attiva solo quando previousPosition < event_time <= currentPosition
 * (passaggio reale nel tempo), non quando si riparte manualmente da un evento.
 */
function checkEvents(currentMs) {
    if (!backend || !eventsData.length) return;
    if (typeof currentMs !== 'number' || !Number.isFinite(currentMs)) return;

    const current = currentMs;
    const previousPosition = lastTimeUpdateMs;
    lastTimeUpdateMs = current;

    const delta = previousPosition > 0 ? Math.abs(current - previousPosition) : 0;
    const SEEK_THRESHOLD_MS = 500;
    if (delta > SEEK_THRESHOLD_MS) return;

    eventsData.forEach(evt => {
        if (current < evt.timestamp_ms - 200) triggeredEventIds.delete(evt.id);
    });

    const sorted = [...eventsData].sort((a, b) => a.timestamp_ms - b.timestamp_ms);
    const reached = sorted.find(evt =>
        previousPosition < evt.timestamp_ms && evt.timestamp_ms <= current && !triggeredEventIds.has(evt.id)
    );

    if (reached) {
        triggeredEventIds.add(reached.id);
        backend.videoPause();
        highlightEventInList(reached.id);
    }
}

/**
 * Callback: Evento appena creato → evidenzia la card nella lista
 */
function onEventCreated(eventId) {
    highlightEventInList(eventId);
}

/**
 * Evidenzia l'evento nella lista (classe selected) e scorre per mostrarlo
 */
function highlightEventInList(eventId) {
    const container = document.getElementById('eventsList');
    if (!container) return;
    let selectedItem = null;
    container.querySelectorAll('.event-list-item').forEach(item => {
        const isSelected = item.dataset.eventId === eventId;
        item.classList.toggle('selected', isSelected);
        if (isSelected) selectedItem = item;
    });
    if (selectedItem) {
        selectedItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

/**
 * Renderizza le clip cards
 */
function renderClips(clips) {
    const container = document.getElementById('clipsContainer');
    if (!container) return;

    const arr = ensureArray(clips);
    container.innerHTML = '';

    arr.forEach(clip => {
        const card = createClipCard(clip);
        container.appendChild(card);
    });
}

/**
 * Crea una clip card
 */
function createClipCard(clip) {
    const card = document.createElement('div');
    card.className = `clip-card ${clip.isPlaying ? 'playing' : ''}`;
    card.dataset.clipId = clip.id;
    
    const editingActive = clip.isEditing;
    card.innerHTML = `
        <div class="clip-header">
            <span class="clip-status-dot"></span>
            <span class="clip-title">${escapeHtml(clip.name)}</span>
        </div>
        <div class="clip-duration">Durata: ${Math.floor(clip.duration / 1000)}s</div>
        <div class="clip-actions-slot">
            <div class="clip-actions" ${editingActive ? 'style="display:none"' : ''}>
                <button class="btn-primary" onclick="playClip('${clip.id}')">
                    Riproduci
                </button>
                <button class="btn-secondary" onclick="editClip('${clip.id}')">
                    Modifica
                </button>
            </div>
            <div class="clip-editing" ${editingActive ? '' : 'style="display:none"'}>
                <div class="edit-buttons">
                    <button class="btn-secondary" onclick="updateClipStart('${clip.id}')">
                        Aggiorna Inizio
                    </button>
                    <button class="btn-secondary" onclick="updateClipEnd('${clip.id}')">
                        Aggiorna Fine
                    </button>
                </div>
                <div class="edit-actions">
                    <button class="btn-primary btn-save-gradient" onclick="saveClipEdit('${clip.id}')">
                        Salva
                    </button>
                    <button class="btn-cancel" onclick="cancelClipEdit('${clip.id}')">
                        Annulla
                    </button>
                </div>
            </div>
        </div>
        <div class="clip-delete">
            <button class="btn-delete" onclick="deleteClip('${clip.id}')">
                Elimina
            </button>
        </div>
    `;
    
    // Click sulla card (escluso pulsanti) → play
    card.addEventListener('click', (e) => {
        if (!e.target.closest('button') && !clip.isEditing) {
            playClip(clip.id);
        }
    });
    
    return card;
}

// Editing functions
function updateClipStart(clipId) {
    if (backend) {
        backend.updateClipStart(clipId);
    }
}

function updateClipEnd(clipId) {
    if (backend) {
        backend.updateClipEnd(clipId);
    }
}

function saveClipEdit(clipId) {
    if (backend) {
        backend.saveClipEdit(clipId);
    }
}

function cancelClipEdit(clipId) {
    if (backend) {
        backend.cancelClipEdit(clipId);
    }
}

function showClipEditingUI(clipId) {
    // La card si aggiorna automaticamente tramite clipsUpdated signal
}

/**
 * Renderizza i pulsanti evento
 */
function renderEventButtons(events) {
    const container = document.getElementById('eventButtons');
    if (!container) return;

    const arr = ensureArray(events);
    container.innerHTML = '';

    arr.forEach(evt => {
        const btn = document.createElement('button');
        btn.className = 'event-btn';
        btn.style.borderLeftColor = evt.color;
        btn.textContent = evt.name;
        btn.onclick = () => createEvent(evt.id);
        container.appendChild(btn);
    });
}

/**
 * Renderizza la lista eventi nel pannello sinistro
 */
function renderEventList(events) {
    const container = document.getElementById('eventsList');
    if (!container) return;

    const arr = ensureArray(events);
    container.innerHTML = '';

    if (arr.length === 0) {
        container.classList.add('event-list-empty');
        return;
    }

    container.classList.remove('event-list-empty');

    // Ordina per timestamp
    const sorted = [...arr].sort((a, b) => (a.timestamp_ms || 0) - (b.timestamp_ms || 0));
    
    sorted.forEach(evt => {
        const typeInfo = eventTypes[evt.event_type_id] || { name: 'Evento' };
        const timeStr = formatTime(evt.timestamp_ms);
        const displayName = evt.label || typeInfo.name;
        
        const item = document.createElement('div');
        item.className = 'event-list-item';
        item.dataset.eventId = evt.id;
        item.style.borderLeftColor = eventColors[evt.event_type_id] || '#888';
        
        item.innerHTML = `
            <div class="event-item-header">
                <input type="text" class="event-item-title" value="${escapeHtml(displayName)}" 
                    placeholder="${escapeHtml(typeInfo.name)}" 
                    data-event-id="${evt.id}"
                    title="Clicca per modificare il titolo">
                <span class="event-item-time">${timeStr}</span>
            </div>
            <textarea class="event-item-desc" rows="3"
                placeholder="Descrizione..."
                data-event-id="${evt.id}">${escapeHtml(evt.description || '')}</textarea>
        `;
        
        // Click sulla riga (esclusi input) → seek
        item.addEventListener('click', (e) => {
            if (e.target.classList.contains('event-item-title') || e.target.classList.contains('event-item-desc')) return;
            if (backend) backend.seekToTimestamp(evt.timestamp_ms);
            container.querySelectorAll('.event-list-item').forEach(i => i.classList.remove('selected'));
            item.classList.add('selected');
            item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
        
        // Double-click sulla riga → seek
        item.addEventListener('dblclick', (e) => {
            if (e.target.classList.contains('event-item-title') || e.target.classList.contains('event-item-desc')) return;
            if (backend) backend.seekToTimestamp(evt.timestamp_ms);
            container.querySelectorAll('.event-list-item').forEach(i => i.classList.remove('selected'));
            item.classList.add('selected');
            item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
        
        // Click destro → menu Elimina
        item.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (eventContextMenuOpen && eventContextMenuOpen.parentNode) {
                eventContextMenuOpen.parentNode.removeChild(eventContextMenuOpen);
                eventContextMenuOpen = null;
            }
            const menu = document.createElement('div');
            menu.className = 'event-context-menu';
            menu.style.cssText = `
                position: fixed;
                left: ${e.clientX}px;
                top: ${e.clientY}px;
                background: var(--bg-elevated);
                border: 1px solid var(--border-emphasis);
                border-radius: 8px;
                padding: 4px 0;
                z-index: 10000;
                box-shadow: var(--shadow-lg);
                min-width: 120px;
            `;
            const eliminaItem = document.createElement('div');
            eliminaItem.textContent = 'Elimina';
            eliminaItem.style.cssText = 'padding: 8px 16px; cursor: pointer; color: #dc2626; font-size: 13px;';
            eliminaItem.addEventListener('mouseenter', () => { eliminaItem.style.background = 'var(--bg-hover)'; });
            eliminaItem.addEventListener('mouseleave', () => { eliminaItem.style.background = 'transparent'; });
            eliminaItem.addEventListener('click', (ev) => {
                ev.stopPropagation();
                if (backend) backend.deleteEvent(evt.id);
                if (menu.parentNode) {
                    document.body.removeChild(menu);
                    eventContextMenuOpen = null;
                }
            });
            menu.appendChild(eliminaItem);
            document.body.appendChild(menu);
            eventContextMenuOpen = menu;
            const close = () => {
                if (menu.parentNode) {
                    document.body.removeChild(menu);
                    eventContextMenuOpen = null;
                }
                document.removeEventListener('click', close);
            };
            setTimeout(() => document.addEventListener('click', close), 10);
        });
        
        container.appendChild(item);
    });
    
    // Bind event handlers per titolo e descrizione
    container.querySelectorAll('.event-item-title').forEach(input => {
        input.addEventListener('blur', function() {
            const id = this.dataset.eventId;
            if (backend && id) backend.updateEventLabel(id, this.value.trim());
        });
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') this.blur();
        });
    });
    
    container.querySelectorAll('.event-item-desc').forEach(ta => {
        ta.addEventListener('blur', function() {
            const id = this.dataset.eventId;
            if (backend && id) backend.updateEventDescription(id, this.value);
        });
    });
}

/**
 * Formatta millisecondi in mm:ss - mai NaN
 */
function formatTime(ms) {
    const n = Number(ms);
    if (typeof ms === 'undefined' || ms === null || !Number.isFinite(n) || n < 0) {
        return '0:00';
    }
    const sec = Math.floor(n / 1000);
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

/**
 * Funzioni chiamate dai pulsanti
 */

function playClip(clipId) {
    if (!backend) return;
    console.log('▶ Play clip:', clipId);
    backend.playClip(clipId);
}

function editClip(clipId) {
    if (!backend) return;
    console.log('✏ Edit clip:', clipId);
    backend.editClip(clipId);
    // Mostra UI editing
    showClipEditingUI(clipId);
}

function deleteClip(clipId) {
    if (!backend) return;
    if (confirm('Eliminare questa clip?')) {
        console.log('🗑 Delete clip:', clipId);
        backend.deleteClip(clipId);
    }
}

function createEvent(eventTypeId) {
    if (!backend) return;
    console.log('➕ Create event:', eventTypeId);
    backend.createEvent(eventTypeId);
}

/**
 * Controlli video
 */

let currentSpeedRate = 1.0;
let skipSeconds = 5;
const SKIP_PRESETS = [3, 5, 10, 30, 60];

function updateSkipButtonLabels() {
    const rw = document.getElementById('btnRewind');
    const fw = document.getElementById('btnForward');
    if (rw) rw.textContent = `-${skipSeconds}s`;
    if (fw) fw.textContent = `+${skipSeconds}s`;
}

let skipIntervalMenuOpen = null;
let eventContextMenuOpen = null;

function showSkipIntervalMenu(e) {
    e.preventDefault();
    e.stopPropagation();
    if (skipIntervalMenuOpen && skipIntervalMenuOpen.parentNode) {
        skipIntervalMenuOpen.parentNode.removeChild(skipIntervalMenuOpen);
        skipIntervalMenuOpen = null;
    }
    const menu = document.createElement('div');
    menu.className = 'skip-interval-menu';
    menu.style.cssText = `
        position: fixed;
        left: ${e.clientX}px;
        top: ${e.clientY}px;
        background: var(--bg-elevated);
        border: 1px solid var(--border-emphasis);
        border-radius: 8px;
        padding: 4px 0;
        z-index: 10000;
        box-shadow: var(--shadow-lg);
        min-width: 140px;
    `;
    [...SKIP_PRESETS, 'custom'].forEach(val => {
        const item = document.createElement('div');
        item.className = 'skip-interval-menu-item';
        item.textContent = val === 'custom' ? 'Personalizzato...' : val + 's';
        item.style.cssText = 'padding: 8px 16px; cursor: pointer; color: var(--text-primary); font-size: 13px;';
        item.addEventListener('mouseenter', () => { item.style.background = 'var(--bg-hover)'; });
        item.addEventListener('mouseleave', () => { item.style.background = 'transparent'; });
        item.addEventListener('click', (ev) => {
            ev.stopPropagation();
            if (val === 'custom') {
                const n = parseInt(prompt('Secondi di skip (1–120):', skipSeconds), 10);
                if (!isNaN(n) && n >= 1 && n <= 120) skipSeconds = n;
            } else {
                skipSeconds = val;
            }
            updateSkipButtonLabels();
            if (menu.parentNode) {
                document.body.removeChild(menu);
                skipIntervalMenuOpen = null;
            }
        });
        menu.appendChild(item);
    });
    document.body.appendChild(menu);
    skipIntervalMenuOpen = menu;
    const close = () => {
        if (menu.parentNode) {
            document.body.removeChild(menu);
            skipIntervalMenuOpen = null;
        }
        document.removeEventListener('click', close);
    };
    setTimeout(() => document.addEventListener('click', close), 10);
}

document.getElementById('btnRewind')?.addEventListener('contextmenu', showSkipIntervalMenu);
document.getElementById('btnForward')?.addEventListener('contextmenu', showSkipIntervalMenu);

document.getElementById('btnRestart')?.addEventListener('click', () => {
    if (backend) {
        backend.restartVideo();
    }
});

document.getElementById('btnSpeed')?.addEventListener('click', (e) => {
    showSpeedMenu(e.target);
});

document.getElementById('btnFrame')?.addEventListener('click', () => {
    if (backend) backend.stepFrame();
});

document.getElementById('btnPlay')?.addEventListener('click', () => {
    if (backend) backend.videoPlay();
});

document.getElementById('btnPause')?.addEventListener('click', () => {
    if (backend) backend.videoPause();
});

document.getElementById('btnRewind')?.addEventListener('click', () => {
    if (backend) backend.videoRewind(skipSeconds);
});

document.getElementById('btnForward')?.addEventListener('click', () => {
    if (backend) backend.videoForward(skipSeconds);
});
document.getElementById('btnPrevEvent')?.addEventListener('click', () => {
    if (backend) backend.goToPrevEvent();
});
document.getElementById('btnNextEvent')?.addEventListener('click', () => {
    if (backend) backend.goToNextEvent();
});

document.getElementById('btnOpenVideo')?.addEventListener('click', () => {
    if (backend) backend.openVideo();
});
document.getElementById('btnCreaEvento')?.addEventListener('click', () => {
    if (backend) backend.createGenericEvent();
});
document.getElementById('btnModificaPulsanti')?.addEventListener('click', () => {
    if (backend) backend.openEventButtonsConfig();
});

document.getElementById('btnShortcuts')?.addEventListener('click', () => {
    if (backend) backend.showShortcutsHelp();
});

document.getElementById('btnClipStart')?.addEventListener('click', () => {
    if (backend) backend.clipStart();
});

document.getElementById('btnClipEnd')?.addEventListener('click', () => {
    if (backend) backend.clipEnd();
});

/**
 * Utility
 */

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Timeline interaction
 */

document.querySelector('.timeline-track')?.addEventListener('click', (e) => {
    if (!backend) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const percent = (e.clientX - rect.left) / rect.width;
    backend.seekPercent(percent);
});

// Timeline aggiornata solo da timeUpdated (no polling)

function updateTimeline(timeData) {
    const progress = document.querySelector('.timeline-progress');
    const handle = document.getElementById('timelineHandle');
    const currentTimeEl = document.getElementById('currentTime');
    const totalTimeEl = document.getElementById('totalTime');
    
    if (!timeData) return;
    
    const current = timeData.current;
    const duration = timeData.duration;
    
    const hasValidDuration = typeof duration === 'number' && Number.isFinite(duration) && duration > 0;
    const hasValidCurrent = typeof current === 'number' && Number.isFinite(current) && current >= 0;
    
    if (progress && handle && hasValidDuration && hasValidCurrent) {
        const percent = Math.min(100, Math.max(0, (current / duration) * 100));
        progress.style.width = `${percent}%`;
        handle.style.left = `${percent}%`;
    }
    
    if (currentTimeEl) {
        currentTimeEl.textContent = hasValidCurrent ? formatTime(current) : '0:00';
    }
    
    if (totalTimeEl) {
        totalTimeEl.textContent = hasValidDuration ? formatTime(duration) : '0:00';
    }
    
    updateTimelineData(timeData);
}

console.log('🚀 Football Analyzer Frontend ready');

/* ============================================
   TIMELINE EVENTI CANVAS
   Replica esatta di EventTimelineBar Qt
   ============================================ */

function initTimelineCanvas() {
    timelineCanvas = document.getElementById('timelineCanvas');
    if (!timelineCanvas) return;
    
    timelineCtx = timelineCanvas.getContext('2d');
    
    // Set canvas size
    const rect = timelineCanvas.getBoundingClientRect();
    timelineCanvas.width = rect.width;
    timelineCanvas.height = 48;
    
    // Click handler per seek
    timelineCanvas.addEventListener('click', (e) => {
        if (!backend || currentDuration <= 0) return;
        
        const rect = timelineCanvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const percent = x / timelineCanvas.width;
        const timestamp = Math.floor(percent * currentDuration);
        
        backend.seekToTimestamp(timestamp);
    });
    
    // Resize handler
    window.addEventListener('resize', () => {
        const rect = timelineCanvas.getBoundingClientRect();
        timelineCanvas.width = rect.width;
        drawTimeline();
    });
    
    // Initial draw
    drawTimeline();
}

function drawTimeline() {
    if (!timelineCtx || !timelineCanvas) return;
    
    const w = timelineCanvas.width;
    const h = timelineCanvas.height;
    const barH = 12;
    const barY = (h - barH) / 2;
    const padding = 10;
    const barW = w - padding * 2;
    
    // Clear canvas
    timelineCtx.clearRect(0, 0, w, h);
    
    // Background track
    timelineCtx.fillStyle = '#243447';
    roundRect(timelineCtx, padding, barY, barW, barH, 4, true, false);
    
    // Border
    timelineCtx.strokeStyle = '#30363D';
    timelineCtx.lineWidth = 1;
    roundRect(timelineCtx, padding, barY, barW, barH, 4, false, true);
    
    if (currentDuration > 0) {
        // Progress bar (position indicator fill)
        const progressPct = currentPosition / currentDuration;
        const progressW = progressPct * barW;
        timelineCtx.fillStyle = '#12a88a';
        roundRect(timelineCtx, padding, barY, progressW, barH, 4, true, false);
        
        // Position line
        const posX = padding + progressW;
        timelineCtx.strokeStyle = '#12a88a';
        timelineCtx.lineWidth = 2;
        timelineCtx.beginPath();
        timelineCtx.moveTo(posX, barY - 4);
        timelineCtx.lineTo(posX, barY + barH + 4);
        timelineCtx.stroke();
        
        // Event markers
        eventsData.forEach(evt => {
            const evtPct = evt.timestamp_ms / currentDuration;
            const evtX = padding + evtPct * barW;
            const color = eventColors[evt.event_type_id] || '#888888';
            
            timelineCtx.fillStyle = color;
            timelineCtx.beginPath();
            timelineCtx.arc(evtX, barY, 5, 0, Math.PI * 2);
            timelineCtx.fill();
        });
    }
}

// Helper: draw rounded rectangle
function roundRect(ctx, x, y, width, height, radius, fill, stroke) {
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + width - radius, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
    ctx.lineTo(x + width, y + height - radius);
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    ctx.lineTo(x + radius, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
    if (fill) ctx.fill();
    if (stroke) ctx.stroke();
}

function updateTimelineData(timeData) {
    if (!timeData) return;
    const d = timeData.duration;
    const c = timeData.current;
    if (typeof d === 'number' && Number.isFinite(d) && d > 0) {
        currentDuration = d;
    }
    if (typeof c === 'number' && Number.isFinite(c) && c >= 0) {
        currentPosition = c;
    }
    drawTimeline();
}

// Update eventi quando cambiano
function updateTimelineEvents(events) {
    eventsData = events || [];
    drawTimeline();
}

/* ============================================
   CONTROLLI PLAYER AVANZATI
   ============================================ */

// Speed menu (replica Qt speed options)
function showSpeedMenu(button) {
    const speeds = [
        { rate: 0.03, label: '0.03x - Super Slow Motion' },
        { rate: 0.25, label: '0.25x - Super rallentato' },
        { rate: 0.5, label: '0.5x - Rallentato' },
        { rate: 1.0, label: '1x - Normale' },
        { rate: 2.0, label: '2x - Molto veloce' },
        { rate: 0.0, label: 'Frame-by-frame - Manuale' }
    ];
    
    // Create simple menu
    const menu = document.createElement('div');
    menu.className = 'speed-menu';
    menu.style.cssText = `
        position: fixed;
        background: var(--bg-elevated);
        border: 1px solid var(--border-emphasis);
        border-radius: 8px;
        padding: 4px 0;
        z-index: 1000;
        box-shadow: var(--shadow-lg);
    `;
    
    const rect = button.getBoundingClientRect();
    menu.style.left = rect.left + 'px';
    menu.style.top = (rect.bottom + 4) + 'px';
    
    speeds.forEach(speed => {
        const item = document.createElement('div');
        item.className = 'speed-menu-item';
        item.textContent = speed.label;
        item.style.cssText = `
            padding: 8px 16px;
            cursor: pointer;
            color: var(--text-primary);
            font-size: 13px;
            white-space: nowrap;
        `;
        item.addEventListener('mouseenter', () => {
            item.style.background = 'var(--bg-hover)';
        });
        item.addEventListener('mouseleave', () => {
            item.style.background = 'transparent';
        });
        item.addEventListener('click', () => {
            currentSpeedRate = speed.rate;
            if (backend) {
                backend.setPlaybackRate(speed.rate);
            }
            button.textContent = speed.rate === 0 ? 'Frame' : speed.rate + 'x';
            document.body.removeChild(menu);
        });
        menu.appendChild(item);
    });
    
    document.body.appendChild(menu);
    
    // Close on click outside
    setTimeout(() => {
        const closeMenu = (e) => {
            if (!menu.contains(e.target) && e.target !== button) {
                document.body.removeChild(menu);
                document.removeEventListener('click', closeMenu);
            }
        };
        document.addEventListener('click', closeMenu);
    }, 100);
}

/* ============================================
   DRAWING SYSTEM
   ============================================ */

// Video Click Handler
let videoClickArea = null;

function initVideoClickHandler() {
    videoClickArea = document.getElementById('videoClickArea');
    if (!videoClickArea) {
        console.error('❌ videoClickArea NOT FOUND!');
        return;
    }
    
    console.log('✅ videoClickArea found:', videoClickArea);
    console.log('   Rect:', videoClickArea.getBoundingClientRect());
    
    videoClickArea.addEventListener('click', handleVideoClick);
    
    // Test immediato
    videoClickArea.style.border = '2px solid lime'; // Debug visual
    console.log('✅ Video click handler initialized with visual border');
}

function handleVideoClick(e) {
    console.log('🎯 handleVideoClick CALLED!', e);
    
    if (!backend) {
        console.error('❌ Backend not available!');
        return;
    }
    
    // Get click position relative to video container
    const rect = videoClickArea.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    console.log('📍 Click coordinates:', { x, y, clientX: e.clientX, clientY: e.clientY });
    
    // Get current video position (synchronous)
    const timestamp = backend.getVideoPosition();
    console.log(`🎬 Video clicked at (${Math.round(x)}, ${Math.round(y)}) - Timestamp: ${timestamp}ms`);
    
    // Notify backend of video click
    if (backend.onVideoClick) {
        backend.onVideoClick(x, y, timestamp);
        console.log('✅ Backend.onVideoClick() called');
    } else {
        console.warn('⚠️ backend.onVideoClick not available');
    }
}

/**
 * Strumenti disegno: collegano pulsanti Web UI al backend Qt (DrawingOverlay)
 */
function initDrawingTools() {
    const toolButtons = {
        'toolCircle': 'circle',
        'toolLine': 'line',
        'toolArrow': 'arrow',
        'toolCurvedArrow': 'curved_arrow',
        'toolParabola': 'parabola_arrow',
        'toolRect': 'rect',
        'toolText': 'text',
        'toolPencil': 'pencil'
    };

    Object.entries(toolButtons).forEach(([btnId, tool]) => {
        const btn = document.getElementById(btnId);
        if (btn && backend) {
            btn.addEventListener('click', () => {
                const wasActive = btn.classList.contains('active');
                Object.keys(toolButtons).forEach(id => {
                    document.getElementById(id)?.classList.remove('active');
                });
                if (!wasActive) {
                    btn.classList.add('active');
                    backend.setDrawTool(tool);
                } else {
                    backend.setDrawTool('none');
                }
            });
        }
    });

    const clearBtn = document.getElementById('btnClearDrawings');
    if (clearBtn && backend) {
        clearBtn.addEventListener('click', () => {
            if (confirm('Cancellare tutti i disegni?')) {
                backend.clearDrawings();
                Object.keys(toolButtons).forEach(id => {
                    document.getElementById(id)?.classList.remove('active');
                });
                backend.setDrawTool('none');
            }
        });
    }

    // Pulsante Colore/Spessore: per ora nessuna azione (il backend non espone setColor/setPenWidth via QWebChannel)
    // Si potrebbe aggiungere in futuro
}

/**
 * Tab Statistiche | Clip nella sidebar destra (stats button; tab switch è in sidebar_right inline)
 */
function initRightSidebarTabs() {
    const btnRefresh = document.getElementById('btnRefreshStats');
    const statsOutput = document.getElementById('statsOutput');
    if (btnRefresh && statsOutput && backend) {
        btnRefresh.addEventListener('click', () => {
            const json = backend.getStatistics();
            const data = safeJsonParse(json);
            statsOutput.textContent = data ? Object.entries(data).map(([k, v]) => `${k}: ${v ?? '-'}`).join('\n') : 'Nessun dato.';
        });
    }
}

