"""
Client RunPod Serverless v2 – Football Analyzer / PRELYT
Flusso:
  1. Upload video su Cloudflare R2 (ottieni URL pubblico)
  2. POST https://api.runpod.io/v2/{endpoint_id}/run  con {"input": {"video_url": url}}
  3. Polling GET /status/{job_id} fino a COMPLETED o FAILED
  4. Scarica JSON risultato da R2 (result_url nel payload)
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

import requests

LOG = logging.getLogger(__name__)

REQUEST_TIMEOUT = 60
POLL_INTERVAL_DEFAULT = 5
RUNPOD_BASE = "https://api.runpod.io/v2"


def _load_env():
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass


def _headers() -> dict:
    _load_env()
    api_key = os.environ.get("RUNPOD_API_KEY", "")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _endpoint_url(path: str = "") -> str:
    _load_env()
    endpoint_id = os.environ.get("RUNPOD_ENDPOINT_ID", "")
    return f"{RUNPOD_BASE}/{endpoint_id}/{path.lstrip('/')}"


def create_job(
    video_path: str,
    options: Optional[dict] = None,
    upload_progress_callback: Optional[Callable[[int, int], None]] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    1. Carica video su R2
    2. POST /run con {"input": {"video_url": url, "options": ...}}
    Returns (job_id, None) oppure (None, errore).
    """
    from r2_storage import upload_video

    remote_key = Path(video_path).name
    LOG.info("Uploading %s to R2...", video_path)
    video_url, err = upload_video(video_path, remote_key, upload_progress_callback)
    if err:
        return None, f"Errore upload R2: {err}"
    LOG.info("R2 URL: %s", video_url)

    payload = {"input": {"video_url": video_url, "options": options or {}}}
    try:
        r = requests.post(
            _endpoint_url("run"),
            json=payload,
            headers=_headers(),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        return None, str(e) or "Errore di connessione"

    if r.status_code in (200, 201):
        try:
            body = r.json()
            job_id = body.get("id")
            if job_id:
                LOG.info("Job creato: %s (status: %s)", job_id, body.get("status"))
                return str(job_id), None
        except Exception:
            pass
        return None, "Risposta server non valida (manca id)"

    return None, r.text[:200] or f"Errore server ({r.status_code})"


def get_status(job_id: str) -> tuple[Optional[dict], Optional[str]]:
    """
    GET /status/{job_id}
    Ritorna (status_dict, None) oppure (None, errore).
    status_dict ha chiavi: id, status, output, error
    RunPod status: IN_QUEUE, IN_PROGRESS, COMPLETED, FAILED, CANCELLED, TIMED_OUT
    """
    try:
        r = requests.get(
            _endpoint_url(f"status/{job_id}"),
            headers=_headers(),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        return None, str(e)

    if r.status_code != 200:
        return None, r.text[:200] or f"Errore {r.status_code}"
    try:
        return r.json(), None
    except Exception:
        return None, "Risposta non valida"


def cancel_job(job_id: str) -> bool:
    """POST /cancel/{job_id} — annulla job in coda."""
    try:
        r = requests.post(
            _endpoint_url(f"cancel/{job_id}"),
            headers=_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        return r.status_code in (200, 201)
    except Exception:
        return False


def run_poll_loop(
    job_id: str,
    on_event: Callable[[dict], None],
    interval_seconds: int = POLL_INTERVAL_DEFAULT,
    stop_check: Optional[Callable[[], bool]] = None,
) -> None:
    """
    Polling /status/{job_id} ogni interval_seconds.
    Invoca on_event con dizionario normalizzato:
      {job_id, status, progress, message, result_url}
    Termina quando status è COMPLETED/FAILED o stop_check() è True.
    """
    TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}

    while True:
        if stop_check and stop_check():
            return

        st, err = get_status(job_id)
        if err:
            on_event({"job_id": job_id, "status": "FAILED", "message": err})
            return

        if st:
            raw_status = st.get("status", "UNKNOWN").upper()
            output = st.get("output") or {}

            # Normalizza evento per l'UI
            event = {
                "job_id": job_id,
                "status": raw_status,
                "progress": output.get("progress", 0) if isinstance(output, dict) else 0,
                "message": output.get("message", raw_status) if isinstance(output, dict) else raw_status,
                "result_url": output.get("result_url") if isinstance(output, dict) else None,
                "error": st.get("error") or (output.get("error") if isinstance(output, dict) else None),
            }
            on_event(event)

            if raw_status in TERMINAL:
                return

        if stop_check and stop_check():
            return
        time.sleep(interval_seconds)
