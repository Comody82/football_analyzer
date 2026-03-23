"""
Backend Bridge per Football Analyzer Web UI
Gestisce la comunicazione bidirezionale tra Python e JavaScript via QWebChannel
"""
import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from PyQt5.QtCore import QObject, Qt, pyqtSignal, pyqtSlot, QTimer, QThread
from PyQt5.QtWidgets import QFileDialog, QApplication, QDialog, QMessageBox, QInputDialog

from core import EventManager, ClipManager, Project, StatisticsManager
from core.events import EventType
from ui.drawing_overlay import DrawTool
from config import DEFAULT_EVENT_TYPES, HIGHLIGHTS_FOLDER, DEFAULT_CLIP_PRE_SECONDS, DEFAULT_CLIP_POST_SECONDS


class BackendBridge(QObject):
    """Bridge tra Python backend e JavaScript frontend"""
    
    # Segnali per aggiornare la UI
    clipsUpdated = pyqtSignal(str)  # JSON delle clip
    statusChanged = pyqtSignal(str)
    playbackStateChanged = pyqtSignal(bool)  # True=playing, False=paused/stopped
    videoLoaded = pyqtSignal(str)  # path video
    eventsUpdated = pyqtSignal(str)  # JSON degli eventi (per timeline)
    eventCreated = pyqtSignal(str)   # id evento appena creato (per selezione card)
    eventTypesUpdated = pyqtSignal(str)  # JSON dei tipi evento (per pulsanti)
    timeUpdated = pyqtSignal(str)  # JSON {current, duration} per barra progresso
    zoomUpdated = pyqtSignal(float)  # livello zoom (1.0–5.0)
    zoomZoneFactorUpdated = pyqtSignal(float)  # fattore zoom zona (1.0–5.0)
    toastRequested = pyqtSignal(str, str)  # (messaggio, tipo: 'info'|'warn')

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
        self._clip_resume_token = 0
        self._clip_last_position_ms = 0
        self._clip_triggered_event_ids = set()
        self.current_project_id = None
        self._download_thread = None
        self._download_worker = None
        self._automatic_events = []  # Fase 8: eventi da event engine (pass, recovery, shot, pressing)

        # Carica tipi evento di default
        self.event_manager.load_default_types(DEFAULT_EVENT_TYPES)
        
        # Connetti aggiornamenti posizione video per barra progresso
        if self.video_player:
            self.video_player.positionChanged.connect(self._emit_time_update)
            self.video_player.durationChanged.connect(self._emit_time_update)
            self.video_player.playbackStateChanged.connect(self.playbackStateChanged.emit)
            if hasattr(self.video_player, 'zoomLevelChanged'):
                self.video_player.zoomLevelChanged.connect(self.zoomUpdated.emit)
            if hasattr(self.video_player, 'zoomZoneFactorChanged'):
                self.video_player.zoomZoneFactorChanged.connect(self.zoomZoneFactorUpdated.emit)
            if self.drawing_overlay and hasattr(self.drawing_overlay, 'zoomZoneCleared'):
                self.drawing_overlay.zoomZoneCleared.connect(lambda: self.zoomZoneFactorUpdated.emit(1.0))
    
    # ==========================================
    # Slots Python chiamati da JavaScript
    # ==========================================
    
    @pyqtSlot(result=str)
    def getClips(self):
        """Restituisce le clip in formato JSON"""
        clips_data = []
        is_player_playing = bool(self.video_player and self.video_player.state() == 1)
        for clip in self.clips:
            pause_duration_sec = int(clip.get('pause_duration_sec', 3))
            is_active = clip['id'] == self.active_clip_id
            clips_data.append({
                'id': clip['id'],
                'name': clip['name'],
                'duration': clip['duration'],
                'start': clip['start'],
                'end': clip['end'],
                'pause_duration_sec': max(0, pause_duration_sec),
                'isActive': is_active,
                'isPlaying': is_active and is_player_playing,
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
        """Riproduce una clip. Pausa, seek, render disegni, poi play."""
        logging.debug(f"Playing clip: {clip_id}")
        clip = self._get_clip_by_id(clip_id)
        if clip and self.video_player:
            self.active_clip_id = clip_id
            self._clip_cancel_pending_resume()
            # Include il boundary di start (evento esatto a clip.start).
            self._clip_last_position_ms = max(0, clip['start'] - 1)
            self._clip_triggered_event_ids.clear()
            self.video_player.pause()
            self.video_player.setPosition(clip['start'])
            if self.parent_window and hasattr(self.parent_window, 'force_render_drawings_at'):
                self.parent_window.force_render_drawings_at(clip['start'])
            def _after_seek():
                if clip_id != self.active_clip_id:
                    return
                if self.parent_window and hasattr(self.parent_window, 'force_render_drawings_at'):
                    self.parent_window.force_render_drawings_at(clip['start'])
                # Se c'è evento al boundary iniziale, applica subito la pausa clip temporizzata.
                reached = self._find_reached_clip_event(
                    clip,
                    max(0, clip['start'] - 1),
                    clip['start'],
                    tolerance_ms=50
                )
                if reached and reached.id not in self._clip_triggered_event_ids:
                    self._clip_triggered_event_ids.add(reached.id)
                    pause_duration_sec = max(0, int(clip.get('pause_duration_sec', 3)))
                    if pause_duration_sec > 0:
                        self._clip_schedule_resume(pause_duration_sec)
                        self._notify_clips_updated()
                        return
                self.video_player.play()
                self._notify_clips_updated()
            QTimer.singleShot(80, _after_seek)
        self.statusChanged.emit(f"Playing: {clip['name'] if clip else 'Unknown'}")

    @pyqtSlot(str)
    def pauseClip(self, clip_id):
        """Pausa solo la clip attiva (non influisce sulla modalità normale)."""
        if not self.video_player or self.active_clip_id != clip_id:
            return
        self._clip_cancel_pending_resume()
        self.video_player.pause()
        self._notify_clips_updated()
        clip = self._get_clip_by_id(clip_id)
        self.statusChanged.emit(f"Clip in pausa: {clip['name'] if clip else clip_id}")

    @pyqtSlot(str)
    def toggleClipPlayback(self, clip_id):
        """Toggle play/pause della clip: start, pausa manuale, resume dalla posizione corrente."""
        if not self.video_player:
            return
        if self.active_clip_id != clip_id:
            # Start clip mode solo da click clip-card toggle.
            self.playClip(clip_id)
            return
        if self.video_player.state() == 1:
            # Pausa manuale in clip mode: non uscire dalla modalità clip.
            self.pauseClip(clip_id)
            return
        # Resume clip mode dalla posizione corrente (senza reset stato trigger).
        self._clip_cancel_pending_resume()
        clip = self._get_clip_by_id(clip_id)
        if not clip:
            return
        if self.video_player.position() >= clip['end']:
            self.video_player.setPosition(clip['start'])
            self._clip_last_position_ms = max(0, clip['start'] - 1)
            self._clip_triggered_event_ids.clear()
            if self.parent_window and hasattr(self.parent_window, 'force_render_drawings_at'):
                self.parent_window.force_render_drawings_at(clip['start'])
        self.video_player.play()
        self._notify_clips_updated()

    @pyqtSlot(str)
    def restartClip(self, clip_id):
        """Riporta la clip all'inizio e mette in pausa, mantenendo clip mode attiva."""
        if not self.video_player:
            return
        clip = self._get_clip_by_id(clip_id)
        if not clip:
            return
        self.active_clip_id = clip_id
        self._clip_cancel_pending_resume()
        self._clip_triggered_event_ids.clear()
        self._clip_last_position_ms = max(0, clip['start'] - 1)
        self.video_player.pause()
        self.video_player.setPosition(clip['start'])
        if self.parent_window and hasattr(self.parent_window, 'force_render_drawings_at'):
            self.parent_window.force_render_drawings_at(clip['start'])
        self._notify_clips_updated()
        self.statusChanged.emit(f"Clip pronta dall'inizio: {clip['name']}")
    
    @pyqtSlot(str)
    def editClip(self, clip_id: str):
        """Entra in modalità modifica clip"""
        logging.debug(f"Editing clip: {clip_id}")
        clip = self._get_clip_by_id(clip_id)
        if clip:
            # Salva backup per annullamento
            self._editing_clip_backup = {
                'start': clip['start'],
                'end': clip['end'],
                'duration': clip['duration'],
                'pause_duration_sec': int(clip.get('pause_duration_sec', 3))
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
            self._clip_cancel_pending_resume()
            self._clip_triggered_event_ids.clear()
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
            self.exit_clip_playback_mode()
            self._clip_cancel_pending_resume()
            self.video_player.play()
            self.statusChanged.emit("Playing")
    
    @pyqtSlot()
    def videoPause(self):
        """Pause video"""
        if self.video_player:
            self._clip_cancel_pending_resume()
            self.video_player.pause()
            self.statusChanged.emit("Paused")

    @pyqtSlot()
    def togglePlayPause(self):
        """Alterna Play/Pausa"""
        if self.video_player:
            st = self.video_player.state()
            # PlayingState = 1, PausedState/StoppedState = 0 o 2
            if st == 1:
                self._clip_cancel_pending_resume()
                self.video_player.pause()
                self.statusChanged.emit("Paused")
            else:
                self.exit_clip_playback_mode()
                self._clip_cancel_pending_resume()
                self.video_player.play()
                self.statusChanged.emit("Playing")

    @pyqtSlot(int)
    def videoRewind(self, seconds):
        """Rewind video di N secondi"""
        if self.video_player:
            self.exit_clip_playback_mode()
            self._clip_cancel_pending_resume()
            pos = max(0, self.video_player.position() - seconds * 1000)
            self.video_player.setPosition(pos)
    
    @pyqtSlot(int)
    def videoForward(self, seconds):
        """Forward video di N secondi"""
        if self.video_player:
            self.exit_clip_playback_mode()
            self._clip_cancel_pending_resume()
            pos = min(self.video_player.duration(), 
                     self.video_player.position() + seconds * 1000)
            self.video_player.setPosition(pos)
    
    @pyqtSlot()
    def restartVideo(self):
        """Restart video dall'inizio e play"""
        if self.video_player:
            self.exit_clip_playback_mode()
            self._clip_cancel_pending_resume()
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
        """Apre sorgente video: file locale oppure link web."""
        parent = self.parent_window or QApplication.activeWindow()
        box = QMessageBox(parent)
        box.setWindowTitle("Apri Video")
        box.setText("Scegli la sorgente del video")
        btn_file = box.addButton("File locale", QMessageBox.AcceptRole)
        btn_link = box.addButton("Link web", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        box.exec_()

        clicked = box.clickedButton()
        if clicked == btn_file:
            self._open_video_from_file_dialog()
        elif clicked == btn_link:
            self._open_video_from_link_dialog()

    def _open_video_from_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Apri Video",
            "",
            "Video Files (*.mp4 *.avi *.mkv *.mov *.webm);;All Files (*.*)"
        )
        if file_path:
            self._load_video_path(file_path)

    def _open_video_from_link_dialog(self):
        parent = self.parent_window or QApplication.activeWindow()
        url, ok = QInputDialog.getText(
            parent,
            "Apri da link",
            "Incolla URL video (YouTube/Facebook supportato se estrattore disponibile):"
        )
        if not ok:
            return
        url = (url or "").strip()
        if not url:
            return
        if not re.match(r"^https?://", url, flags=re.IGNORECASE):
            QMessageBox.warning(parent, "URL non valido", "Inserisci un link http/https valido.")
            return
        self._start_video_download(url)

    def _load_video_path(self, file_path: str):
        if file_path and self.video_player:
            self.video_player.load(file_path)
            self.project.video_path = file_path
            self.videoLoaded.emit(file_path)
            self.statusChanged.emit(f"Video caricato: {Path(file_path).name}")

    def _start_video_download(self, url: str):
        parent = self.parent_window or QApplication.activeWindow()
        if shutil.which("yt-dlp") is None:
            QMessageBox.warning(
                parent,
                "Dipendenza mancante",
                "yt-dlp non trovato. Installa yt-dlp per usare i link web."
            )
            return
        if self._download_thread is not None:
            QMessageBox.information(parent, "Download in corso", "Attendi la fine del download corrente.")
            return

        downloads_dir = (Path(__file__).parent / "data" / "downloads").absolute()
        downloads_dir.mkdir(parents=True, exist_ok=True)

        self._download_thread = QThread(self)
        self._download_worker = _VideoDownloadWorker(url, str(downloads_dir))
        self._download_worker.moveToThread(self._download_thread)
        self._download_thread.started.connect(self._download_worker.run)
        self._download_worker.status.connect(self.statusChanged.emit)
        self._download_worker.failed.connect(self._on_video_download_failed)
        self._download_worker.finished.connect(self._on_video_download_finished)
        self._download_worker.finished.connect(self._download_thread.quit)
        self._download_worker.failed.connect(self._download_thread.quit)
        self._download_thread.finished.connect(self._cleanup_download_worker)
        self._download_thread.start()
        self.statusChanged.emit("Download video avviato...")

    @pyqtSlot(str)
    def _on_video_download_finished(self, file_path: str):
        self._load_video_path(file_path)

    @pyqtSlot(str)
    def _on_video_download_failed(self, message: str):
        parent = self.parent_window or QApplication.activeWindow()
        QMessageBox.warning(parent, "Download fallito", message)
        self.statusChanged.emit("Download video fallito")

    @pyqtSlot()
    def _cleanup_download_worker(self):
        if self._download_worker is not None:
            self._download_worker.deleteLater()
            self._download_worker = None
        if self._download_thread is not None:
            self._download_thread.deleteLater()
            self._download_thread = None
    
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
                    'duration': end - start,
                    'pause_duration_sec': 3
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
    @pyqtSlot(str, int)
    def saveClipEdit(self, clip_id, pause_duration_sec=3):
        """Salva modifiche clip ed esce da editing"""
        clip = self._get_clip_by_id(clip_id)
        if self.editing_clip_id == clip_id and clip:
            clip['pause_duration_sec'] = max(0, int(pause_duration_sec))
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
            clip['pause_duration_sec'] = self._editing_clip_backup['pause_duration_sec']
        self.editing_clip_id = None
        self._editing_clip_backup = None
        self._notify_clips_updated()
        self.statusChanged.emit("Modifiche annullate")
    
    @pyqtSlot(float)
    def seekPercent(self, percent):
        """Seek video alla percentuale specificata"""
        if self.video_player:
            self.exit_clip_playback_mode()
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

    @pyqtSlot(result=bool)
    def isVideoPlaying(self):
        """Ritorna True se il player è in riproduzione."""
        return bool(self.video_player and self.video_player.state() == 1)
    
    @pyqtSlot(str)
    def setAutomaticEvents(self, events_json):
        """Imposta eventi automatici (event engine) per timeline. events_json: array JSON."""
        try:
            self._automatic_events = json.loads(events_json) if isinstance(events_json, str) else (events_json or [])
        except Exception:
            self._automatic_events = []
        self.eventsUpdated.emit(self.getEvents())

    @pyqtSlot(result=str)
    def getEvents(self):
        """Restituisce tutti gli eventi (manuali + automatici) in formato JSON per timeline."""
        events_data = []
        for evt in self.event_manager.get_events():
            events_data.append({
                'id': evt.id,
                'event_type_id': evt.event_type_id,
                'timestamp_ms': evt.timestamp_ms,
                'description': evt.description,
                'label': evt.label
            })
        labels = {"pass": "Passaggio", "recovery": "Recupero", "shot": "Tiro", "pressing": "Pressing"}
        for i, e in enumerate(self._automatic_events):
            t = e.get("type", "event")
            events_data.append({
                'id': f"auto_{i}",
                'event_type_id': f"auto_{t}",
                'timestamp_ms': e.get("timestamp_ms", 0),
                'description': labels.get(t, t),
                'label': labels.get(t, t)
            })
        return json.dumps(events_data)
    
    @pyqtSlot(int)
    def seekToTimestamp(self, timestamp_ms):
        """Seek video al timestamp specificato. Mette in pausa, seek, forza render disegni."""
        if self.video_player:
            self.exit_clip_playback_mode()
            self._clip_cancel_pending_resume()
            if self.parent_window and hasattr(self.parent_window, 'force_render_drawings_at'):
                self.parent_window._seek_target_ms = timestamp_ms
            self.video_player.pause()
            self.video_player.setPosition(timestamp_ms)
            if self.parent_window and hasattr(self.parent_window, 'force_render_drawings_at'):
                self.parent_window.force_render_drawings_at(timestamp_ms)
                self.parent_window._seek_target_ms = None
            self.statusChanged.emit(f"Seek to {timestamp_ms}ms")
    
    def _get_all_events_sorted(self):
        """Lista unificata (manuali + automatici) ordinata per timestamp_ms, ogni elemento ha .timestamp_ms e .id."""
        class _E:
            __slots__ = ("timestamp_ms", "id")
            def __init__(self, ts, id_):
                self.timestamp_ms = ts
                self.id = id_
        out = [_E(evt.timestamp_ms, evt.id) for evt in self.event_manager.get_events()]
        for i, e in enumerate(self._automatic_events):
            out.append(_E(e.get("timestamp_ms", 0), f"auto_{i}"))
        return sorted(out, key=lambda x: x.timestamp_ms)

    @pyqtSlot()
    def goToPrevEvent(self):
        """Vai all'evento precedente (manuali + automatici)."""
        if not self.video_player:
            return
        self.exit_clip_playback_mode()
        pos = self.video_player.position()
        events = [e for e in self._get_all_events_sorted() if e.timestamp_ms < pos]
        if not events:
            return
        prev_evt = max(events, key=lambda e: e.timestamp_ms)
        self.video_player.setPosition(prev_evt.timestamp_ms)
        self.video_player.pause()

    @pyqtSlot()
    def goToNextEvent(self):
        """Vai all'evento successivo (manuali + automatici)."""
        if not self.video_player:
            return
        self.exit_clip_playback_mode()
        pos = self.video_player.position()
        events = [e for e in self._get_all_events_sorted() if e.timestamp_ms > pos]
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
            "polygon": DrawTool.POLYGON,
            "text": DrawTool.TEXT, "pencil": DrawTool.PENCIL, "zoom": DrawTool.ZOOM,
            "zoom_zone": DrawTool.ZOOM_ZONE, "none": DrawTool.NONE,
        }
        tool = name_map.get((tool_name or "").lower(), DrawTool.NONE)
        self.drawing_overlay.setTool(tool)
        if tool == DrawTool.ZOOM:
            if self.drawing_overlay and hasattr(self.drawing_overlay, 'clearZoomZone'):
                self.drawing_overlay.clearZoomZone()
        elif tool == DrawTool.ZOOM_ZONE:
            if self.video_player and hasattr(self.video_player, 'setZoomLevel'):
                self.video_player.setZoomLevel(1.0)
                self.zoomUpdated.emit(1.0)
            if self.video_player and hasattr(self.video_player, 'getZoomZoneFactor'):
                self.zoomZoneFactorUpdated.emit(self.video_player.getZoomZoneFactor())
        if self.parent_window and hasattr(self.parent_window, "_on_draw_tool_changed"):
            self.parent_window._on_draw_tool_changed(tool)

    @pyqtSlot()
    def clearDrawings(self):
        """Cancella tutti i disegni dall'overlay."""
        if self.drawing_overlay:
            self.drawing_overlay.clearDrawings()
            self.statusChanged.emit("Disegni cancellati")

    @pyqtSlot()
    def clearZoomZone(self):
        """Rimuove la zona zoom."""
        if self.drawing_overlay and hasattr(self.drawing_overlay, 'clearZoomZone'):
            self.drawing_overlay.clearZoomZone()

    @pyqtSlot()
    def showShortcutsHelp(self):
        """Mostra dialog scorciatoie da tastiera (chiamabile da Web UI)."""
        if self.parent_window and hasattr(self.parent_window, '_show_shortcuts_help'):
            self.parent_window._show_shortcuts_help()

    @pyqtSlot()
    def backToProjects(self):
        """Ritorna alla dashboard progetti."""
        if self.parent_window and hasattr(self.parent_window, "_go_back_to_dashboard"):
            self.parent_window._go_back_to_dashboard()

    @pyqtSlot(str)
    def frontendReady(self, area):
        """Notifica che una sezione web (left/center/right) ha completato il bootstrap."""
        area_name = (area or "").strip().lower()
        if self.parent_window and hasattr(self.parent_window, "_on_frontend_ready"):
            self.parent_window._on_frontend_ready(area_name)

    @pyqtSlot()
    def openHighlightsStudio(self):
        """Apre lo studio highlights nel workspace."""
        if self.parent_window and hasattr(self.parent_window, "show_highlights_studio"):
            self.parent_window.show_highlights_studio()

    @pyqtSlot()
    def openFieldCalibration(self):
        """Apre il dialog di calibrazione campo per analisi automatica."""
        if self.parent_window and hasattr(self.parent_window, "show_field_calibration"):
            self.parent_window.show_field_calibration()

    @pyqtSlot()
    def openVideoPreprocessing(self):
        """Apre il dialog di preprocessing video per analisi automatica."""
        if self.parent_window and hasattr(self.parent_window, "show_video_preprocessing"):
            self.parent_window.show_video_preprocessing()

    @pyqtSlot()
    def openPlayerDetection(self):
        """Apre il dialog di player detection per analisi automatica."""
        if self.parent_window and hasattr(self.parent_window, "show_player_detection"):
            self.parent_window.show_player_detection()

    @pyqtSlot()
    def openPlayerTracking(self):
        """Apre il dialog di player tracking per analisi automatica."""
        if self.parent_window and hasattr(self.parent_window, "show_player_tracking"):
            self.parent_window.show_player_tracking()

    @pyqtSlot()
    def openBallDetection(self):
        """Apre il dialog di ball detection per analisi automatica."""
        if self.parent_window and hasattr(self.parent_window, "show_ball_detection"):
            self.parent_window.show_ball_detection()

    @pyqtSlot()
    def openFullAnalysis(self):
        """Apre dialog opzioni e avvia analisi automatica completa (preprocess + player + ball + clustering)."""
        if self.parent_window and hasattr(self.parent_window, "show_full_analysis"):
            self.parent_window.show_full_analysis()

    @pyqtSlot()
    def openReclusterTeams(self):
        """Esegue solo il clustering globale squadre sui dati già presenti."""
        if self.parent_window and hasattr(self.parent_window, "show_recluster_teams"):
            self.parent_window.show_recluster_teams()

    @pyqtSlot()
    def loadTrackingOverlay(self):
        """Ricarica e applica i dati di tracking (ball/player) dal progetto."""
        if self.parent_window and hasattr(self.parent_window, "_load_tracking_overlay"):
            self.parent_window._load_tracking_overlay()

    @pyqtSlot(result=bool)
    def toggleTrackingOverlay(self):
        """Attiva/disattiva overlay tracking sul video. Ritorna True se ora visibile."""
        if not self.video_player or not hasattr(self.video_player, "setShowTracking"):
            QMessageBox.warning(
                self.parent_window or QApplication.activeWindow(),
                "Tracking",
                "Nessun video caricato.",
            )
            return False
        # Ricarica sempre i dati prima di mostrare
        self.loadTrackingOverlay()
        has_ball = bool(getattr(self.video_player, "_ball_tracks", None))
        has_player = bool(getattr(self.video_player, "_player_tracks", None))
        if not has_ball and not has_player:
            QMessageBox.information(
                self.parent_window or QApplication.activeWindow(),
                "Mostra tracking",
                "Nessun dato di tracking trovato.\n\n"
                "Esegui prima Ball detection e/o Player detection + Player tracking "
                "dal progetto aperto, poi riprova.",
            )
            return False

        def _has_any_detection(tracks, key_frame="frames", key_det="detections", key_single="detection"):
            if not tracks:
                return False
            frames = tracks.get(key_frame, [])
            for f in frames:
                if key_single and key_single in f:
                    if f.get(key_single):
                        return True
                if key_det and f.get(key_det):
                    return True
            return False

        has_ball_det = _has_any_detection(getattr(self.video_player, "_ball_tracks", None), key_det=None, key_single="detection")
        has_player_det = _has_any_detection(getattr(self.video_player, "_player_tracks", None), key_single=None, key_det="detections")
        if not has_ball_det and not has_player_det:
            QMessageBox.information(
                self.parent_window or QApplication.activeWindow(),
                "Mostra tracking",
                "L'analisi non ha rilevato giocatori né palla in nessun frame.\n\n"
                "Possibili cause:\n"
                "• Inquadratura molto larga o angolo sfavorevole\n"
                "• Qualità/resoluzione bassa\n"
                "• Prova con un altro video dove i giocatori sono ben visibili\n\n"
                "L'overlay è attivo ma non ci sono elementi da mostrare.",
            )

        new_state = not self.video_player.getShowTracking()
        self.video_player.setShowTracking(new_state)
        if self.video_player.duration() > 0:
            self.video_player.setPosition(self.video_player.position())  # forza redraw
        self.statusChanged.emit("Tracking " + ("attivato" if new_state else "disattivato"))
        return new_state

    @pyqtSlot(result=bool)
    def getTrackingOverlayVisible(self):
        """Ritorna True se l'overlay tracking è visibile."""
        if not self.video_player or not hasattr(self.video_player, "getShowTracking"):
            return False
        return self.video_player.getShowTracking()

    @pyqtSlot()
    def windowMinimize(self):
        """Minimizza finestra principale."""
        if self.parent_window:
            self.parent_window.window().showMinimized()

    @pyqtSlot()
    def windowToggleMaximize(self):
        """Toggle maximize/normal finestra principale."""
        if not self.parent_window:
            return
        win = self.parent_window.window()
        if win.isMaximized():
            win.showNormal()
        else:
            win.showMaximized()

    @pyqtSlot()
    def windowClose(self):
        """Chiude finestra principale."""
        if self.parent_window:
            self.parent_window.window().close()

    @pyqtSlot(int, int)
    def startWindowDrag(self, global_x, global_y):
        """Inizia drag finestra dalla topbar HTML."""
        if self.parent_window and hasattr(self.parent_window, "_start_window_drag"):
            self.parent_window._start_window_drag(global_x, global_y)

    @pyqtSlot(int, int)
    def moveWindowDrag(self, global_x, global_y):
        """Continua drag finestra."""
        if self.parent_window and hasattr(self.parent_window, "_move_window_drag"):
            self.parent_window._move_window_drag(global_x, global_y)

    @pyqtSlot()
    def endWindowDrag(self):
        """Termina drag finestra."""
        if self.parent_window and hasattr(self.parent_window, "_end_window_drag"):
            self.parent_window._end_window_drag()

    @pyqtSlot(result=float)
    def getZoomLevel(self):
        """Livello zoom corrente (1.0–5.0)."""
        if self.video_player and hasattr(self.video_player, 'zoomLevel'):
            return self.video_player.zoomLevel()
        return 1.0

    @pyqtSlot(float)
    def setZoomFromSlider(self, level: float):
        """Imposta zoom da barra (zoom centrato sul video)."""
        if not self.video_player or not hasattr(self.video_player, 'setZoomAt'):
            return
        level = max(1.0, min(5.0, float(level)))
        vp = self.video_player._graphics_view.viewport()
        cx = vp.width() // 2
        cy = vp.height() // 2
        self.video_player.setZoomAt(level, cx, cy)

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
                self._normalize_clip(clip)
                return clip
        return None
    
    def _notify_clips_updated(self):
        """Notifica JavaScript che le clip sono cambiate"""
        for clip in self.clips:
            self._normalize_clip(clip)
        clips_json = self.getClips()
        self.clipsUpdated.emit(clips_json)
    
    def _emit_time_update(self):
        """Emette aggiornamento tempo per la barra progresso. Ferma clip al raggiungimento della fine."""
        if self.active_clip_id and self.video_player:
            clip = self._get_clip_by_id(self.active_clip_id)
            pos = self.video_player.position()
            previous = self._clip_last_position_ms
            if clip and pos >= clip['end']:
                self._clip_cancel_pending_resume()
                self.video_player.pause()
                self.active_clip_id = None
                self._clip_triggered_event_ids.clear()
                self._notify_clips_updated()
            elif clip and self.video_player.state() == 1:
                self._check_clip_event_pause(clip, previous, pos)
            self._clip_last_position_ms = pos
        self.timeUpdated.emit(self.getCurrentTime())

    def _check_clip_event_pause(self, clip, previous_ms, current_ms):
        """Pausa temporizzata solo durante la riproduzione clip."""
        if previous_ms < 0:
            return
        if abs(current_ms - previous_ms) > 500:
            return
        events = sorted(self.event_manager.get_events(), key=lambda e: e.timestamp_ms)
        for evt in events:
            if current_ms < evt.timestamp_ms - 200:
                self._clip_triggered_event_ids.discard(evt.id)
        reached = self._find_reached_clip_event(clip, previous_ms, current_ms, tolerance_ms=50)
        if not reached:
            return
        self._clip_triggered_event_ids.add(reached.id)
        pause_duration_sec = max(0, int(clip.get('pause_duration_sec', 3)))
        if pause_duration_sec <= 0:
            return
        self.video_player.pause()
        self._clip_schedule_resume(pause_duration_sec)

    def _find_reached_clip_event(self, clip, previous_ms, current_ms, tolerance_ms=50):
        """Trova il primo evento raggiunto nel range clip con tolleranza temporale."""
        lower = min(previous_ms, current_ms) - tolerance_ms
        upper = max(previous_ms, current_ms) + tolerance_ms
        for evt in sorted(self.event_manager.get_events(), key=lambda e: e.timestamp_ms):
            if evt.id in self._clip_triggered_event_ids:
                continue
            # Boundary inclusivo: evento a clip.start è valido.
            if not (evt.timestamp_ms >= clip['start'] and evt.timestamp_ms <= clip['end']):
                continue
            if lower <= evt.timestamp_ms <= upper:
                return evt
        return None

    def _clip_schedule_resume(self, pause_duration_sec):
        """Programma ripresa clip con token cancellabile."""
        self._clip_resume_token += 1
        resume_token = self._clip_resume_token

        def resume_playback():
            if resume_token != self._clip_resume_token:
                return
            if not self.video_player or not self.active_clip_id:
                return
            clip = self._get_clip_by_id(self.active_clip_id)
            if not clip:
                return
            if self.video_player.position() >= clip['end']:
                return
            self.video_player.play()

        QTimer.singleShot(int(pause_duration_sec * 1000), resume_playback)

    def _clip_cancel_pending_resume(self):
        """Cancella eventuale resume clip pendente (invalidando il token)."""
        self._clip_resume_token += 1

    def exit_clip_playback_mode(self):
        """Esce dalla modalità clip playback: reset stato + timer + selezione card."""
        was_active = self.active_clip_id is not None
        self.active_clip_id = None
        self._clip_cancel_pending_resume()
        self._clip_triggered_event_ids.clear()
        if was_active:
            self._notify_clips_updated()

    def _normalize_clip(self, clip):
        """Applica default/validazione ai campi clip."""
        clip['pause_duration_sec'] = max(0, int(clip.get('pause_duration_sec', 3)))

    def _run_ffmpeg(self, cmd):
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            )
            if proc.returncode != 0:
                logging.warning("FFmpeg error: %s", (proc.stderr or proc.stdout or "").strip())
                return False
            return True
        except Exception as ex:
            logging.warning("Errore esecuzione ffmpeg: %s", ex)
            return False

    def _render_clip_segment(self, source_video: str, start_ms: int, end_ms: int, out_path: Path) -> bool:
        start_sec = max(0.0, float(start_ms) / 1000.0)
        duration_sec = max(0.1, (float(end_ms) - float(start_ms)) / 1000.0)
        vf = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p"
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{start_sec:.3f}",
            "-i", str(source_video),
            "-t", f"{duration_sec:.3f}",
            "-vf", vf,
            "-r", "25",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-c:a", "aac",
            "-ar", "44100",
            "-ac", "2",
            "-movflags", "+faststart",
            str(out_path),
        ]
        return self._run_ffmpeg(cmd)

    def _render_image_segment(self, image_path: str, duration_sec: int, out_path: Path) -> bool:
        dur = max(1, int(duration_sec))
        vf = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-t", str(dur),
            "-i", str(image_path),
            "-f", "lavfi",
            "-t", str(dur),
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-shortest",
            "-vf", vf,
            "-r", "25",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-c:a", "aac",
            "-ar", "44100",
            "-ac", "2",
            "-movflags", "+faststart",
            str(out_path),
        ]
        return self._run_ffmpeg(cmd)

    def generate_highlights_package_from_sequence(
        self, sequence, output_path=None, progress_callback=None
    ):
        """
        Genera highlights dalla sequenza ordinata.
        sequence: [{"type":"clip","clip_id":"..."}, {"type":"image","path":"...","duration_sec":3}, ...]
        output_path: path dove salvare (opzionale). Se None, usa cartella Highlights.
        progress_callback: fn(percent: int, status: str) opzionale.
        Ritorna tuple (ok: bool, result: str).
        """
        if not self.clip_manager.is_available():
            return False, "FFmpeg non trovato. Installa FFmpeg per generare highlights."

        source_video = str(getattr(self.project, "video_path", "") or "").strip()
        if not source_video or not Path(source_video).exists():
            return False, "Video sorgente non disponibile."

        sequence = list(sequence or [])
        if not sequence:
            return False, "Sequenza vuota."

        def _report(pct, msg):
            if progress_callback:
                progress_callback(pct, msg)

        clips_by_id = {c.get("id"): c for c in self.clips if c.get("id")}
        valid_items = []
        for it in sequence:
            if (it or {}).get("type") == "clip":
                if clips_by_id.get((it or {}).get("clip_id")):
                    valid_items.append(it)
            elif (it or {}).get("type") == "image":
                p = str((it or {}).get("path", "")).strip()
                if p and Path(p).exists():
                    valid_items.append(it)
        total_segments = len(valid_items)
        if total_segments == 0:
            return False, "Nessun contenuto valido nella sequenza."

        highlights_dir = Path(HIGHLIGHTS_FOLDER)
        highlights_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix="hl_", dir=str(highlights_dir)))

        try:
            segment_paths = []
            seg_idx = 0

            for idx, item in enumerate(sequence):
                it = item or {}
                if it.get("type") == "clip":
                    clip = clips_by_id.get(it.get("clip_id"))
                    if not clip:
                        continue
                    _report(int(90 * seg_idx / total_segments), f"Rendering clip {seg_idx + 1}/{total_segments}...")
                    out_seg = tmp_dir / f"seg_clip_{seg_idx:03d}.mp4"
                    seg_idx += 1
                    if not self._render_clip_segment(source_video, int(clip["start"]), int(clip["end"]), out_seg):
                        return False, "Errore durante rendering clip highlights."
                    segment_paths.append(out_seg)
                elif it.get("type") == "image":
                    p = str(it.get("path", "")).strip()
                    d = max(1, int(it.get("duration_sec", 3) or 3))
                    if not p or not Path(p).exists():
                        continue
                    _report(int(90 * seg_idx / total_segments), f"Rendering immagine {seg_idx + 1}/{total_segments}...")
                    out_seg = tmp_dir / f"seg_img_{seg_idx:03d}.mp4"
                    seg_idx += 1
                    if not self._render_image_segment(p, d, out_seg):
                        return False, "Errore durante rendering immagini highlights."
                    segment_paths.append(out_seg)

            if not segment_paths:
                return False, "Nessun segmento generato."

            _report(92, "Assemblaggio finale...")
            list_file = tmp_dir / "segments.txt"
            with open(list_file, "w", encoding="utf-8") as f:
                for seg in segment_paths:
                    seg_posix = str(seg.absolute()).replace("\\", "/")
                    f.write(f"file '{seg_posix}'\n")

            if output_path:
                out_path = Path(output_path)
                out_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                output_name = f"highlights_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                out_path = highlights_dir / output_name
            cmd_concat = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_file),
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "22",
                "-c:a", "aac",
                "-ar", "44100",
                "-ac", "2",
                "-movflags", "+faststart",
                str(out_path),
            ]
            if not self._run_ffmpeg(cmd_concat):
                return False, "Errore assemblaggio highlights finale."

            _report(100, "Completato!")
            if not out_path.exists():
                return False, "File highlights non creato."
            return True, str(out_path.absolute())
        finally:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
    
    def add_test_clips(self):
        """Aggiunge clip di test per demo"""
        import uuid
        test_clips = [
            {'id': str(uuid.uuid4()), 'name': 'Gol al 15°', 'start': 900000, 'end': 903000, 'duration': 3000, 'pause_duration_sec': 3},
            {'id': str(uuid.uuid4()), 'name': 'Azione 1° tempo', 'start': 1200000, 'end': 1207000, 'duration': 7000, 'pause_duration_sec': 3},
            {'id': str(uuid.uuid4()), 'name': 'Corner', 'start': 1500000, 'end': 1505000, 'duration': 5000, 'pause_duration_sec': 3},
        ]
        self.clips.extend(test_clips)
        self._notify_clips_updated()

    # ==========================================
    # Persistenza progetto (routing dashboard/workspace)
    # ==========================================

    def export_workspace_state(self) -> dict:
        """Esporta stato workspace in forma serializzabile."""
        return {
            "version": 1,
            "project": self.project.to_dict(),
            "events": self.event_manager.to_dict(),
            "clips": list(self.clips),
        }

    def import_workspace_state(self, data: dict):
        """Importa stato workspace senza alterare logiche runtime."""
        payload = data or {}
        self.project.from_dict(payload.get("project", {}))
        events_data = payload.get("events")
        if events_data:
            self.event_manager.from_dict(events_data)
        else:
            # Mantiene i tipi default se il file è vuoto/legacy.
            self.event_manager.clear_events()
        self.clips = list(payload.get("clips", []))
        for clip in self.clips:
            self._normalize_clip(clip)
        self.active_clip_id = None
        self.editing_clip_id = None
        self._editing_clip_backup = None
        self._clip_cancel_pending_resume()
        self._clip_triggered_event_ids.clear()
        self.eventsUpdated.emit(self.getEvents())
        self._notify_clips_updated()
        self.eventTypesUpdated.emit(self.getEventTypes())

    def load_project_from_path(self, project_id: str, project_file_path: str):
        """Carica uno specifico progetto da file associato al projectId."""
        self.current_project_id = project_id
        p = Path(project_file_path)
        if not p.exists():
            self.import_workspace_state({})
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.import_workspace_state(data)
        except Exception as ex:
            logging.warning(f"Errore caricamento progetto {project_id}: {ex}")
            self.import_workspace_state({})

    def save_project_to_path(self, project_file_path: str) -> bool:
        """Salva lo stato corrente del workspace su file."""
        p = Path(project_file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self.export_workspace_state(), f, indent=2, ensure_ascii=False)
            return True
        except Exception as ex:
            logging.warning(f"Errore salvataggio progetto: {ex}")
            return False

    @pyqtSlot(result=int)
    def getCurrentPositionMs(self):
        if self.video_player:
            return int(getattr(self.video_player, '_position_ms', 0) or 0)
        return 0

    @pyqtSlot(result=str)
    def getPlayerTracksJson(self):
        if self.video_player:
            tracks = getattr(self.video_player, '_player_tracks', None)
            if tracks:
                return json.dumps(tracks)
        return '{}'

    @pyqtSlot(result=str)
    def getBallTracksJson(self):
        if self.video_player:
            tracks = getattr(self.video_player, '_ball_tracks', None)
            if tracks:
                return json.dumps(tracks)
        return '{}'

    def _check_video_integrity(self, path: str):
        """
        Verifica che il file video sia leggibile e abbia almeno un frame.
        Ritorna (True, '') se OK, oppure (False, messaggio_errore).
        """
        import cv2
        from pathlib import Path
        p = Path(path)
        if not p.exists():
            return False, f"File non trovato:\n{path}"
        if p.stat().st_size == 0:
            return False, f"Il file video è vuoto:\n{p.name}"
        cap = cv2.VideoCapture(str(p))
        if not cap.isOpened():
            cap.release()
            return False, f"Impossibile aprire il video:\n{p.name}\n\nFormato non supportato o file corrotto."
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        if frames is not None and frames <= 0:
            return False, f"Il video non contiene frame:\n{p.name}"
        return True, ''

    @pyqtSlot(result=bool)
    def toggleTacticalBoard(self):
        if self.parent_window and hasattr(self.parent_window, 'web_view_tactical'):
            tb = self.parent_window.web_view_tactical
            visible = not tb.isVisible()
            tb.setVisible(visible)
            return visible
        return False

    @pyqtSlot(result=bool)
    def toggleHeatmap(self):
        if self.parent_window and hasattr(self.parent_window, 'web_view_heatmap'):
            hm = self.parent_window.web_view_heatmap
            visible = not hm.isVisible()
            hm.setVisible(visible)
            return visible
        return False

    @pyqtSlot(result=str)
    def getHeatmapData(self):
        """Calcola griglie di densità per heatmap e pressing map."""
        COLS, ROWS = 40, 26

        def empty_grid():
            return [[0.0] * COLS for _ in range(ROWS)]

        try:
            tracks = getattr(self.video_player, '_player_tracks', None) if self.video_player else None
            if not tracks or not tracks.get("frames"):
                return json.dumps({
                    "grid_all": empty_grid(), "grid_a": empty_grid(), "grid_b": empty_grid(),
                    "track_grids": {}, "track_ids": [],
                    "pressing_all": empty_grid(), "pressing_a": empty_grid(), "pressing_b": empty_grid(),
                    "has_pressing": False, "cols": COLS, "rows": ROWS,
                })

            frames = tracks.get("frames", [])
            w = max(1, int(tracks.get("width", 1) or 1))
            h = max(1, int(tracks.get("height", 1) or 1))

            grid_all = empty_grid()
            grid_a   = empty_grid()
            grid_b   = empty_grid()
            track_grids = {}
            track_ids = set()

            # Sample every 5th frame for performance
            for fi, frame_data in enumerate(frames):
                if fi % 5 != 0:
                    continue
                for det in frame_data.get("detections", []):
                    if det.get("role") in ("ball", "goal", "referee"):
                        continue
                    cx = (det.get("x", 0) + det.get("w", 0) * 0.5) / w
                    cy = (det.get("y", 0) + det.get("h", 0) * 0.5) / h
                    col = max(0, min(COLS - 1, int(cx * COLS)))
                    row = max(0, min(ROWS - 1, int(cy * ROWS)))
                    team = det.get("team", -1)
                    tid  = det.get("track_id", -1)

                    grid_all[row][col] += 1
                    if team == 0:
                        grid_a[row][col] += 1
                    elif team == 1:
                        grid_b[row][col] += 1
                    if tid >= 0:
                        track_ids.add(tid)
                        if tid not in track_grids:
                            track_grids[tid] = empty_grid()
                        track_grids[tid][row][col] += 1

            # Pressing: aggregate positions near pressing events
            pressing_all = empty_grid()
            pressing_a   = empty_grid()
            pressing_b   = empty_grid()
            pressing_evts = [e for e in self._automatic_events if e.get("type") == "pressing"]
            has_pressing = bool(pressing_evts)
            if pressing_evts:
                fps = 25.0
                for pe in pressing_evts:
                    fi_center = int(pe.get("timestamp_ms", 0) * fps / 1000)
                    for offset in range(-25, 26, 5):
                        fii = fi_center + offset
                        if not (0 <= fii < len(frames)):
                            continue
                        for det in frames[fii].get("detections", []):
                            if det.get("role") in ("ball", "goal", "referee"):
                                continue
                            cx = (det.get("x", 0) + det.get("w", 0) * 0.5) / w
                            cy = (det.get("y", 0) + det.get("h", 0) * 0.5) / h
                            col = max(0, min(COLS - 1, int(cx * COLS)))
                            row = max(0, min(ROWS - 1, int(cy * ROWS)))
                            team = det.get("team", -1)
                            pressing_all[row][col] += 1
                            if team == 0:
                                pressing_a[row][col] += 1
                            elif team == 1:
                                pressing_b[row][col] += 1

            return json.dumps({
                "grid_all":    grid_all,
                "grid_a":      grid_a,
                "grid_b":      grid_b,
                "track_grids": {str(k): v for k, v in track_grids.items()},
                "track_ids":   sorted(list(track_ids)),
                "pressing_all": pressing_all,
                "pressing_a":   pressing_a,
                "pressing_b":   pressing_b,
                "has_pressing": has_pressing,
                "cols": COLS,
                "rows": ROWS,
            })
        except Exception as e:
            return json.dumps({
                "error": str(e), "cols": COLS, "rows": ROWS,
                "grid_all": empty_grid(), "grid_a": empty_grid(), "grid_b": empty_grid(),
                "track_grids": {}, "track_ids": [],
                "pressing_all": empty_grid(), "pressing_a": empty_grid(), "pressing_b": empty_grid(),
                "has_pressing": False,
            })

    @pyqtSlot(result=str)
    def getAiEvents(self):
        """Restituisce gli eventi automatici (event engine) come JSON per events.html."""
        labels = {"pass": "Passaggio", "recovery": "Recupero", "shot": "Tiro", "pressing": "Pressing"}
        result = []
        for i, e in enumerate(self._automatic_events):
            t = e.get("type", "event")
            result.append({
                "id": f"auto_{i}",
                "type": t,
                "label": labels.get(t, t),
                "timestamp_ms": e.get("timestamp_ms", 0),
                "confidence": e.get("confidence", 0.0),
            })
        return json.dumps(result)

    @pyqtSlot(result=float)
    def getTrackingFps(self):
        """Restituisce FPS dei player tracks (usato da tactical board e heatmap)."""
        if self.video_player:
            tracks = getattr(self.video_player, '_player_tracks', None)
            if tracks:
                return float(tracks.get("fps", 3.0))
        return 3.0

    @pyqtSlot(str, str)
    def requestToast(self, message, toast_type="info"):
        """Permette al JS di richiedere un toast Qt. toast_type: 'info'|'warn'|'error'."""
        self.toastRequested.emit(message, toast_type)


class _VideoDownloadWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, url: str, downloads_dir: str):
        super().__init__()
        self.url = url
        self.downloads_dir = Path(downloads_dir)

    @pyqtSlot()
    def run(self):
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_template = str((self.downloads_dir / f"%(title).100s-{ts}-%(id)s.%(ext)s").absolute())
            cmd = [
                "yt-dlp",
                "--no-playlist",
                "--no-warnings",
                "--newline",
                "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
                "--merge-output-format", "mp4",
                "--print", "after_move:filepath",
                "-o", output_template,
                self.url
            ]

            self.status.emit("Download in corso...")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            )

            maybe_file = None
            percent_re = re.compile(r"(\d+(?:\.\d+)?)%")
            for line in proc.stdout:
                txt = (line or "").strip()
                if not txt:
                    continue
                pct = percent_re.search(txt)
                if pct:
                    self.status.emit(f"Download {pct.group(1)}%")
                if txt.lower().endswith((".mp4", ".mkv", ".webm", ".mov", ".m4v")):
                    maybe_file = txt

            return_code = proc.wait()
            if return_code != 0:
                self.failed.emit("Impossibile scaricare il video dal link fornito.")
                return

            if maybe_file and Path(maybe_file).exists():
                self.finished.emit(str(Path(maybe_file).absolute()))
                return

            latest = self._latest_downloaded_video()
            if latest:
                self.finished.emit(str(latest.absolute()))
                return

            self.failed.emit("Download completato ma file non trovato.")
        except Exception as ex:
            self.failed.emit(f"Errore download: {ex}")

    def _latest_downloaded_video(self):
        candidates = []
        for ext in ("*.mp4", "*.mkv", "*.webm", "*.mov", "*.m4v"):
            candidates.extend(self.downloads_dir.glob(ext))
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)
