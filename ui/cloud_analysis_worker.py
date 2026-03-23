"""
Worker Qt per analisi in cloud (RunPod Serverless v2).
Flusso: upload R2 → pre-signed URLs → POST /run → polling /status → download result.
Emette segnali per progresso, risultato pronto, fallimento, errore.
"""
from __future__ import annotations

import logging
import requests as _requests

from PyQt5.QtCore import QThread, pyqtSignal

from cloud_client import (
    POLL_INTERVAL_DEFAULT,
    create_job,
    cancel_job,
    run_poll_loop,
)

LOG = logging.getLogger(__name__)


class CloudAnalysisWorker(QThread):
    """
    Esegue in un thread separato:
      1. Upload video su R2 + generazione pre-signed URL
      2. POST job su RunPod Serverless
      3. Polling /status fino a COMPLETED o FAILED
      4. Download JSON risultati da R2
      5. Emit result_ready con payload pronto per la UI
    """

    status_updated = pyqtSignal(dict)  # { job_id, status, progress, message, result_url }
    result_ready   = pyqtSignal(dict)  # payload risultato per load_analysis_result()
    job_failed     = pyqtSignal(str, str)  # job_id, message
    error          = pyqtSignal(str)       # errore connessione / upload

    def __init__(
        self,
        video_path: str,
        options: dict | None = None,
        poll_interval_seconds: int = POLL_INTERVAL_DEFAULT,
        parent=None,
    ):
        super().__init__(parent)
        self._video_path = video_path
        self._options = options or {}
        self._poll_interval = poll_interval_seconds
        self._cancelled = False
        self._job_id: str | None = None

    def cancel(self):
        self._cancelled = True
        if self._job_id:
            try:
                cancel_job(self._job_id)
            except Exception:
                pass

    def _upload_progress(self, sent: int, total: int):
        """Callback upload R2 → aggiorna progress bar (0-30%)."""
        if total > 0:
            pct = int(30 * sent / total)
            self.status_updated.emit({
                "job_id": "",
                "status": "UPLOADING",
                "progress": pct,
                "message": f"Upload video... {pct}%",
            })

    def _handle_event(self, ev: dict) -> None:
        """Callback polling RunPod: mappa lo stato su progress 30-90%."""
        raw_status = ev.get("status", "").upper()
        base_progress = 30

        if raw_status == "IN_QUEUE":
            pct = 32
            msg = "In coda su RunPod..."
        elif raw_status == "IN_PROGRESS":
            pct = 60
            msg = "Analisi GPU in corso..."
        else:
            pct = base_progress
            msg = raw_status

        self.status_updated.emit({
            "job_id": ev.get("job_id", ""),
            "status": raw_status,
            "progress": pct,
            "message": msg,
        })

    def _download_result(self, result_url: str) -> dict | None:
        """
        Scarica il JSON detections da R2 e lo converte nel formato
        atteso da load_analysis_result():
          {
            "tracking": { "player_tracks": <detections_json>, "ball_tracks": None },
            "events":   { "automatic": [] }
          }
        Il formato detections (frames/detections) è compatibile con player_tracks.
        """
        self.status_updated.emit({
            "job_id": self._job_id or "",
            "status": "DOWNLOADING",
            "progress": 90,
            "message": "Download risultati...",
        })
        try:
            r = _requests.get(result_url, timeout=60)
            r.raise_for_status()
            detections_json = r.json()
        except Exception as e:
            LOG.error("Download risultato fallito: %s", e)
            return None

        # Wrap in formato atteso dall'UI
        return {
            "tracking": {
                "player_tracks": detections_json,
                "ball_tracks": None,
            },
            "events": {
                "automatic": [],
            },
            "_source": "cloud",
            "_result_url": result_url,
        }

    def run(self) -> None:
        if self._cancelled:
            return

        # 1. Upload video + generazione pre-signed URL + submit job
        self.status_updated.emit({
            "job_id": "",
            "status": "UPLOADING",
            "progress": 5,
            "message": "Upload video su cloud...",
        })

        job_id, err = create_job(
            self._video_path,
            self._options,
            upload_progress_callback=self._upload_progress,
        )
        if err or not job_id:
            self.error.emit(err or "Impossibile creare il job RunPod")
            return
        self._job_id = job_id

        self.status_updated.emit({
            "job_id": job_id,
            "status": "IN_QUEUE",
            "progress": 32,
            "message": "Job inviato — in coda su RunPod...",
        })

        if self._cancelled:
            return

        # 2. Polling finché COMPLETED / FAILED
        result_url: str | None = None
        error_msg: str | None = None
        final_status = "UNKNOWN"

        def on_event(ev: dict):
            nonlocal result_url, error_msg, final_status
            self._handle_event(ev)
            final_status = ev.get("status", "").upper()
            if final_status == "COMPLETED":
                result_url = ev.get("result_url")
            elif final_status in ("FAILED", "CANCELLED", "TIMED_OUT"):
                error_msg = ev.get("error") or ev.get("message") or "Analisi fallita"

        run_poll_loop(
            job_id,
            on_event,
            interval_seconds=self._poll_interval,
            stop_check=lambda: self._cancelled,
        )

        if self._cancelled:
            return

        # 3. Gestisci risultato finale
        if final_status == "COMPLETED" and result_url:
            payload = self._download_result(result_url)
            if payload:
                self.status_updated.emit({
                    "job_id": job_id,
                    "status": "COMPLETED",
                    "progress": 100,
                    "message": "Analisi completata!",
                })
                self.result_ready.emit(payload)
            else:
                self.job_failed.emit(job_id, "Impossibile scaricare i risultati da R2")
        elif final_status == "COMPLETED" and not result_url:
            self.job_failed.emit(job_id, "Analisi completata ma result_url mancante")
        else:
            self.job_failed.emit(job_id, error_msg or f"Analisi terminata con stato: {final_status}")
