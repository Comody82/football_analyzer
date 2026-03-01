"""
Backend Bridge per Football Analyzer Web UI
Gestisce la comunicazione bidirezionale tra Python e JavaScript via QWebChannel
"""
import json
import logging
from pathlib import Path
from PyQt5.QtCore import QObject, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QFileDialog, QApplication, QDialog

from core import EventManager, ClipManager, Project, StatisticsManager
from core.events import EventType
from ui.drawing_overlay import DrawTool
from config import DEFAULT_EVENT_TYPES, HIGHLIGHTS_FOLDER, DEFAULT_CLIP_PRE_SECONDS, DEFAULT_CLIP_POST_SECONDS


class BackendBridge(QObject):
    """Bridge tra Python backend e JavaScript frontend"""
    
    # Segnali per aggiornare la UI
    clipsUpdated = pyqtSignal(str)  # JSON delle clip
    statusChanged = pyqtSignal(str)
    videoLoaded = pyqtSignal(str)  # path video
    eventsUpdated = pyqtSignal(str)  # JSON degli eventi (per timeline)
    eventCreated = pyqtSignal(str)   # id evento appena creato (per selezione card)
    eventTypesUpdated = pyqtSignal(str)  # JSON dei tipi evento (per pulsanti)
    timeUpdated = pyqtSignal(str)  # JSON {current, duration} per barra progresso
    
    def __init__(self, video_player=None, drawing_overlay=None, parent_window=None):
        super().__init__()
        self.video_player = video_player
        self.drawing_overlay = drawing_overlay
        self.parent_window = parent_window
        self.event_manager = EventManager()
        self.clip_manager = ClipManager(HIGHLIGHTS_FOLDER)
        self.stats_manager = StatisticsManager(self.event_manager)
        self.project = Project()
        self.clips = []
        self.active_clip_id = None
        self.editing_clip_id = None
        self._editing_clip_backup = None
        
        # Carica tipi evento di default
        self.event_manager.load_default_types(DEFAULT_EVENT_TYPES)
        
        # Connetti aggiornamenti posizione video per barra progresso
        if self.video_player:
            self.video_player.positionChanged.connect(self._emit_time_update)
            self.video_player.durationChanged.connect(self._emit_time_update)
    
    # ==========================================
    # Slots Python chiamati da JavaScript
    # ==========================================
    
    @pyqtSlot(result=str)
    def getClips(self):
        """Restituisce le clip in formato JSON"""
        clips_data = []
        for clip in self.clips:
            clips_data.append({
                'id': clip['id'],
                'name': clip['name'],
                'duration': clip['duration'],
                'start': clip['start'],
                'end': clip['end'],
                'isPlaying': clip['id'] == self.active_clip_id,
                'isEditing': clip['id'] == self.editing_clip_id
            })
        return json.dumps(clips_data)
    
    @pyqtSlot(result=str)
    def getEventTypes(self):
        """Restituisce i tipi di evento in formato JSON"""
        events_data = []
        for evt in self.event_manager.get_event_types():
            events_data.append({
                'id': evt.id,
                'name': evt.name,
                'emoji': evt.icon,
                'color': evt.color
            })
        return json.dumps(events_data)
    
    @pyqtSlot(str)
    def playClip(self, clip_id):
        """Riproduce una clip"""
        logging.debug(f"Playing clip: {clip_id}")
        clip = self._get_clip_by_id(clip_id)
        if clip and self.video_player:
            self.active_clip_id = clip_id
            self.video_player.setPosition(clip['start'])
            self.video_player.play()
            self._notify_clips_updated()
        self.statusChanged.emit(f"Playing: {clip['name'] if clip else 'Unknown'}")
    
    @pyqtSlot(str)
    def editClip(self, clip_id):
        """Entra in modalità modifica clip"""
        logging.debug(f"Editing clip: {clip_id}")
        clip = self._get_clip_by_id(clip_id)
        if clip:
            # Salva backup per annullamento
            self._editing_clip_backup = {
                'start': clip['start'],
                'end': clip['end'],
                'duration': clip['duration']
            }
            self.editing_clip_id = clip_id
            if self.video_player:
                self.video_player.setPosition(clip['start'])
                self.video_player.pause()
            self._notify_clips_updated()
        self.statusChanged.emit("Modalità modifica attiva")
    
    @pyqtSlot(str)
    def deleteClip(self, clip_id):
        """Elimina una clip"""
        logging.debug(f"Deleting clip: {clip_id}")
        self.clips = [c for c in self.clips if c['id'] != clip_id]
        if self.active_clip_id == clip_id:
            self.active_clip_id = None
        if self.editing_clip_id == clip_id:
            self.editing_clip_id = None
        self._notify_clips_updated()
        self.statusChanged.emit("Clip eliminata")
    
    @pyqtSlot(str)
    def createEvent(self, event_type_id):
        """Crea un nuovo evento. Mette in pausa il video per mantenere il timestamp stabile."""
        logging.debug(f"Creating event: {event_type_id}")
        if self.video_player:
            self.video_player.pause()
            self.video_player.setPlaybackRate(1.0)
            timestamp = self.video_player.position()
            event_type = self.event_manager.get_event_type(event_type_id)
            if event_type:
                event = self.event_manager.add_event(event_type_id, timestamp)
                if event:
                    self.statusChanged.emit(f"Evento '{event_type.name}' creato")
                    self.eventsUpdated.emit(self.getEvents())
                    self.eventCreated.emit(event.id)
    
    @pyqtSlot()
    def createGenericEvent(self):
        """Crea un evento generico 'Nuovo Evento' alla posizione corrente"""
        if self.video_player:
            self.video_player.pause()
            self.video_player.setPlaybackRate(1.0)
            timestamp = self.video_player.position()
            evt = self.event_manager.add_event("evento", timestamp, label="Nuovo Evento")
            if evt:
                self.statusChanged.emit("Evento creato")
                self.eventsUpdated.emit(self.getEvents())
                self.eventCreated.emit(evt.id)
    
    @pyqtSlot()
    def openEventButtonsConfig(self):
        """Apre il dialog di configurazione pulsanti evento"""
        try:
            from ui.event_buttons_config_dialog import (
                EventButtonsConfigDialog,
                save_event_types_as_default,
                clear_default_config,
            )
            from PyQt5.QtWidgets import QMessageBox
            
            current = self.event_manager.get_event_types()
            parent = self.parent_window or QApplication.activeWindow()
            dlg = EventButtonsConfigDialog(current, parent)
            if dlg.exec_() == QDialog.Accepted:
                new_types = dlg.get_event_types()
                if not new_types:
                    QMessageBox.warning(
                        parent, "Attenzione",
                        "Deve restare almeno un pulsante evento."
                    )
                    return
                self.event_manager.load_event_types(new_types)
                self.eventTypesUpdated.emit(self.getEventTypes())  # Refresh event buttons
                if dlg.save_as_default():
                    if save_event_types_as_default(new_types):
                        self.statusChanged.emit("Configurazione salvata come predefinita")
                    else:
                        QMessageBox.warning(parent, "Errore", "Impossibile salvare la configurazione")
                else:
                    clear_default_config()
                    self.statusChanged.emit("Modifiche applicate solo a questa sessione")
        except Exception as ex:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(
                self.parent_window or QApplication.activeWindow(),
                "Errore", str(ex)
            )
    
    @pyqtSlot()
    def videoPlay(self):
        """Play video"""
        if self.video_player:
            self.video_player.play()
            self.statusChanged.emit("Playing")
    
    @pyqtSlot()
    def videoPause(self):
        """Pause video"""
        if self.video_player:
            self.video_player.pause()
            self.statusChanged.emit("Paused")

    @pyqtSlot()
    def togglePlayPause(self):
        """Alterna Play/Pausa"""
        if self.video_player:
            st = self.video_player.state()
            # PlayingState = 1, PausedState/StoppedState = 0 o 2
            if st == 1:
                self.video_player.pause()
                self.statusChanged.emit("Paused")
            else:
                self.video_player.play()
                self.statusChanged.emit("Playing")

    @pyqtSlot(int)
    def videoRewind(self, seconds):
        """Rewind video di N secondi"""
        if self.video_player:
            pos = max(0, self.video_player.position() - seconds * 1000)
            self.video_player.setPosition(pos)
    
    @pyqtSlot(int)
    def videoForward(self, seconds):
        """Forward video di N secondi"""
        if self.video_player:
            pos = min(self.video_player.duration(), 
                     self.video_player.position() + seconds * 1000)
            self.video_player.setPosition(pos)
    
    @pyqtSlot()
    def restartVideo(self):
        """Restart video dall'inizio e play"""
        if self.video_player:
            self.video_player.setPosition(0)
            self.video_player.play()
            self.statusChanged.emit("Restarted")
    
    @pyqtSlot(float)
    def setPlaybackRate(self, rate):
        """Imposta velocità riproduzione"""
        if self.video_player:
            self.video_player.setPlaybackRate(rate)
            if rate == 0:
                self.statusChanged.emit("Frame-by-frame mode")
            else:
                self.statusChanged.emit(f"Speed: {rate}x")
    
    @pyqtSlot()
    def stepFrame(self):
        """Avanza di un frame"""
        if self.video_player:
            self.video_player.stepForward()
            self.statusChanged.emit("Step frame")
    
    @pyqtSlot()
    def openVideo(self):
        """Apre dialog per selezionare video"""
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Apri Video",
            "",
            "Video Files (*.mp4 *.avi *.mkv *.mov);;All Files (*.*)"
        )
        if file_path and self.video_player:
            self.video_player.load(file_path)
            self.project.video_path = file_path
            self.videoLoaded.emit(file_path)
            self.statusChanged.emit(f"Video caricato: {Path(file_path).name}")
    
    @pyqtSlot()
    def clipStart(self):
        """Segna inizio clip"""
        if self.video_player:
            timestamp = self.video_player.position()
            logging.debug(f"Clip start: {timestamp}ms")
            self.temp_clip_start = timestamp
            self.statusChanged.emit("Inizio clip marcato")
    
    @pyqtSlot()
    def clipEnd(self):
        """Segna fine clip e crea la clip"""
        if self.video_player and hasattr(self, 'temp_clip_start'):
            start = self.temp_clip_start
            end = self.video_player.position()
            if end > start:
                import uuid
                clip_id = str(uuid.uuid4())
                clip = {
                    'id': clip_id,
                    'name': f"Clip {len(self.clips) + 1}",
                    'start': start,
                    'end': end,
                    'duration': end - start
                }
                self.clips.append(clip)
                logging.debug(f"Clip created: {clip['name']}, duration: {clip['duration']}ms")
                self._notify_clips_updated()
                self.statusChanged.emit(f"Clip creata: {clip['name']}")
                delattr(self, 'temp_clip_start')
            else:
                self.statusChanged.emit("Errore: Fine deve essere dopo Inizio")
    
    @pyqtSlot(str)
    def updateClipStart(self, clip_id):
        """Aggiorna start della clip in editing"""
        clip = self._get_clip_by_id(clip_id)
        if clip and self.video_player:
            new_start = self.video_player.position()
            clip['start'] = new_start
            if clip['end'] <= clip['start']:
                clip['end'] = clip['start'] + 1000
            clip['duration'] = clip['end'] - clip['start']
            self.video_player.setPosition(clip['start'])
            self._notify_clips_updated()
            self.statusChanged.emit("Inizio aggiornato")
    
    @pyqtSlot(str)
    def updateClipEnd(self, clip_id):
        """Aggiorna end della clip in editing"""
        clip = self._get_clip_by_id(clip_id)
        if clip and self.video_player:
            new_end = self.video_player.position()
            clip['end'] = new_end
            if clip['end'] <= clip['start']:
                clip['start'] = max(0, clip['end'] - 1000)
            clip['duration'] = clip['end'] - clip['start']
            self._notify_clips_updated()
            self.statusChanged.emit("Fine aggiornata")
    
    @pyqtSlot(str)
    def saveClipEdit(self, clip_id):
        """Salva modifiche clip ed esce da editing"""
        if self.editing_clip_id == clip_id:
            self.editing_clip_id = None
            self._editing_clip_backup = None
            self._notify_clips_updated()
            self.statusChanged.emit("Modifiche salvate")
    
    @pyqtSlot(str)
    def cancelClipEdit(self, clip_id):
        """Annulla modifiche e ripristina backup"""
        clip = self._get_clip_by_id(clip_id)
        if clip and self._editing_clip_backup:
            clip['start'] = self._editing_clip_backup['start']
            clip['end'] = self._editing_clip_backup['end']
            clip['duration'] = self._editing_clip_backup['duration']
        self.editing_clip_id = None
        self._editing_clip_backup = None
        self._notify_clips_updated()
        self.statusChanged.emit("Modifiche annullate")
    
    @pyqtSlot(float)
    def seekPercent(self, percent):
        """Seek video alla percentuale specificata"""
        if self.video_player:
            pos = int(self.video_player.duration() * percent)
            self.video_player.setPosition(pos)
    
    @pyqtSlot(result=str)
    def getCurrentTime(self):
        """Restituisce tempo corrente del video"""
        if self.video_player:
            return json.dumps({
                'current': self.video_player.position(),
                'duration': self.video_player.duration()
            })
        return json.dumps({'current': 0, 'duration': 0})
    
    @pyqtSlot(result=str)
    def getEvents(self):
        """Restituisce tutti gli eventi in formato JSON"""
        events_data = []
        for evt in self.event_manager.get_events():
            events_data.append({
                'id': evt.id,
                'event_type_id': evt.event_type_id,
                'timestamp_ms': evt.timestamp_ms,
                'description': evt.description,
                'label': evt.label
            })
        return json.dumps(events_data)
    
    @pyqtSlot(int)
    def seekToTimestamp(self, timestamp_ms):
        """Seek video al timestamp specificato. Mette in pausa per mostrare eventuali disegni."""
        if self.video_player:
            self.video_player.pause()
            self.video_player.setPosition(timestamp_ms)
            self.statusChanged.emit(f"Seek to {timestamp_ms}ms")
    
    @pyqtSlot()
    def goToPrevEvent(self):
        """Vai all'evento precedente"""
        if not self.video_player:
            return
        pos = self.video_player.position()
        events = [e for e in self.event_manager.get_events() if e.timestamp_ms < pos]
        if not events:
            return
        prev_evt = max(events, key=lambda e: e.timestamp_ms)
        self.video_player.setPosition(prev_evt.timestamp_ms)
        self.video_player.pause()
    
    @pyqtSlot()
    def goToNextEvent(self):
        """Vai all'evento successivo"""
        if not self.video_player:
            return
        pos = self.video_player.position()
        events = [e for e in self.event_manager.get_events() if e.timestamp_ms > pos]
        if not events:
            return
        next_evt = min(events, key=lambda e: e.timestamp_ms)
        self.video_player.setPosition(next_evt.timestamp_ms)
        self.video_player.pause()
    
    @pyqtSlot()
    def goToPrevEvent(self):
        """Vai all'evento precedente"""
        if not self.video_player:
            return
        pos = self.video_player.position()
        events = [e for e in self.event_manager.get_events() if e.timestamp_ms < pos]
        if not events:
            return
        prev_evt = max(events, key=lambda e: e.timestamp_ms)
        self.video_player.setPosition(prev_evt.timestamp_ms)
        self.video_player.pause()
    
    @pyqtSlot()
    def goToNextEvent(self):
        """Vai all'evento successivo"""
        if not self.video_player:
            return
        pos = self.video_player.position()
        events = [e for e in self.event_manager.get_events() if e.timestamp_ms > pos]
        if not events:
            return
        next_evt = min(events, key=lambda e: e.timestamp_ms)
        self.video_player.setPosition(next_evt.timestamp_ms)
        self.video_player.pause()
    
    @pyqtSlot(str, str)
    def updateEventLabel(self, event_id, label):
        """Aggiorna il titolo/label di un evento"""
        if self.event_manager.update_event_label(event_id, label.strip() or None):
            self.eventsUpdated.emit(self.getEvents())
    
    @pyqtSlot(str)
    def deleteEvent(self, event_id):
        """Elimina un evento"""
        if self.event_manager.remove_event(event_id):
            self.eventsUpdated.emit(self.getEvents())
            self.statusChanged.emit("Evento eliminato")

    @pyqtSlot(str, str)
    def updateEventDescription(self, event_id, description):
        """Aggiorna la descrizione di un evento"""
        self.event_manager.update_event_description(event_id, description or "")
    
    @pyqtSlot(str)
    def setDrawTool(self, tool_name):
        """Imposta strumento disegno (circle, arrow, line, rect, text, pencil, none)."""
        if not self.drawing_overlay:
            return
        name_map = {
            "circle": DrawTool.CIRCLE, "arrow": DrawTool.ARROW, "line": DrawTool.LINE,
            "curved_arrow": DrawTool.CURVED_ARROW, "parabola_arrow": DrawTool.PARABOLA_ARROW,
            "rect": DrawTool.RECTANGLE, "rectangle": DrawTool.RECTANGLE,
            "text": DrawTool.TEXT, "pencil": DrawTool.PENCIL, "none": DrawTool.NONE,
        }
        tool = name_map.get((tool_name or "").lower(), DrawTool.NONE)
        self.drawing_overlay.setTool(tool)
        if self.parent_window and hasattr(self.parent_window, "_on_draw_tool_changed"):
            self.parent_window._on_draw_tool_changed(tool)

    @pyqtSlot()
    def clearDrawings(self):
        """Cancella tutti i disegni dall'overlay."""
        if self.drawing_overlay:
            self.drawing_overlay.clearDrawings()
            self.statusChanged.emit("Disegni cancellati")

    @pyqtSlot()
    def showShortcutsHelp(self):
        """Mostra dialog scorciatoie da tastiera (chiamabile da Web UI)."""
        if self.parent_window and hasattr(self.parent_window, '_show_shortcuts_help'):
            self.parent_window._show_shortcuts_help()

    @pyqtSlot(result=int)
    def getVideoPosition(self):
        """Ritorna posizione corrente video in ms"""
        if self.video_player:
            return self.video_player.position()
        return 0
    
    @pyqtSlot(float, float, int)
    def onVideoClick(self, x, y, timestamp):
        """Gestisce click sull'area video"""
        logging.debug(f"Video click: x={x:.0f}, y={y:.0f}, timestamp={timestamp}ms")
        # Qui possiamo aggiungere logica per:
        # - Creare eventi al timestamp cliccato
        # - Impostare marcatori
        # - Altro...
        self.statusChanged.emit(f"Video clicked at {timestamp}ms")
    
    # ==========================================
    # Metodi interni
    # ==========================================

    @pyqtSlot(result=str)
    def getStatistics(self):
        """Restituisce statistiche in formato JSON"""
        duration_ms = 0
        if self.video_player:
            duration_ms = self.video_player.duration()
        stats = self.stats_manager.compute(duration_ms)
        summary = self.stats_manager.get_summary_dict(stats)
        return json.dumps(summary)

    def _get_clip_by_id(self, clip_id):
        """Trova clip per ID"""
        for clip in self.clips:
            if clip['id'] == clip_id:
                return clip
        return None
    
    def _notify_clips_updated(self):
        """Notifica JavaScript che le clip sono cambiate"""
        clips_json = self.getClips()
        self.clipsUpdated.emit(clips_json)
    
    def _emit_time_update(self):
        """Emette aggiornamento tempo per la barra progresso. Ferma clip al raggiungimento della fine."""
        if self.active_clip_id and self.video_player:
            clip = self._get_clip_by_id(self.active_clip_id)
            pos = self.video_player.position()
            if clip and pos >= clip['end']:
                self.video_player.pause()
                self.active_clip_id = None
                self._notify_clips_updated()
        self.timeUpdated.emit(self.getCurrentTime())
    
    def add_test_clips(self):
        """Aggiunge clip di test per demo"""
        import uuid
        test_clips = [
            {'id': str(uuid.uuid4()), 'name': 'Gol al 15°', 'start': 900000, 'end': 903000, 'duration': 3000},
            {'id': str(uuid.uuid4()), 'name': 'Azione 1° tempo', 'start': 1200000, 'end': 1207000, 'duration': 7000},
            {'id': str(uuid.uuid4()), 'name': 'Corner', 'start': 1500000, 'end': 1505000, 'duration': 5000},
        ]
        self.clips.extend(test_clips)
        self._notify_clips_updated()
