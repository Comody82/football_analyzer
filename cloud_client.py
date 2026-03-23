"""
Client RunPod Serverless v2 – Football Analyzer / PRELYT
Flusso:
  1. Upload video su Cloudflare R2
  2. Genera pre-signed URL per: modello (GET), video (GET), risultato (PUT)
  3. POST https://api.runpod.ai/v2/{endpoint_id}/run  con {input: {video_url, model_url, ...}}
  4. Polling GET /status/{job_id} fino a COMPLETED o FAILED
  5. Il result_url nel payload punta al JSON dei risultati su R2
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

import requests

LOG = logging.getLogger(__name__)

REQUEST_TIMEOUT = 60
POLL_INTERVAL_DEFAULT = 5
RUNPOD_BASE = "https://api.runpod.ai/v2"
PRESIGNED_EXPIRES = 7200  # 2 ore — sufficiente per qualsiasi job


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


def _r2_client():
    """Crea boto3 S3 client per Cloudflare R2."""
    import boto3
    _load_env()
    client = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    bucket = os.environ.get("R2_BUCKET_NAME", "match-analysis-videos")
    public_base = os.environ.get("R2_PUBLIC_URL", "").rstrip("/")
    return client, bucket, public_base


def _generate_presigned_urls(video_key: str) -> dict:
    """
    Genera pre-signed URL per:
      - GET modello (models/best_ckpt.pth)
      - GET video (video_key)
      - PUT risultato (results/{stem}_detections.json)
    Ritorna dict con model_url, video_url, result_put_url, result_url.
    """
    client, bucket, public_base = _r2_client()

    model_url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": "models/best_ckpt.pth"},
        ExpiresIn=PRESIGNED_EXPIRES,
    )

    video_url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": video_key},
        ExpiresIn=PRESIGNED_EXPIRES,
    )

    video_stem = Path(video_key).stem
    result_key = f"results/{video_stem}_detections.json"
    result_put_url = client.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": result_key, "ContentType": "application/json"},
        ExpiresIn=PRESIGNED_EXPIRES,
    )
    result_public_url = f"{public_base}/{result_key}"

    return {
        "model_url": model_url,
        "video_url": video_url,
        "result_put_url": result_put_url,
        "result_url": result_public_url,
        "result_key": result_key,
    }


def create_job(
    video_path: str,
    options: Optional[dict] = None,
    upload_progress_callback: Optional[Callable[[int, int], None]] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    1. Carica video su R2
    2. Genera pre-signed URL per modello, video e risultato
    3. POST /run con {input: {video_url, model_url, result_put_url, result_url, options}}
    Returns (job_id, None) oppure (None, errore).
    """
    from r2_storage import upload_video

    remote_key = Path(video_path).name
    LOG.info("Uploading %s to R2...", video_path)
    _, err = upload_video(video_path, remote_key, upload_progress_callback)
    if err:
        return None, f"Errore upload R2: {err}"
    LOG.info("Video uploaded to R2: %s", remote_key)

    # Genera pre-signed URL (modello + video + risultato)
    try:
        urls = _generate_presigned_urls(remote_key)
        LOG.info("Pre-signed URLs generati (scadono in %ds)", PRESIGNED_EXPIRES)
    except Exception as e:
        return None, f"Errore generazione pre-signed URL: {e}"

    payload = {
        "input": {
            "video_url": urls["video_url"],
            "model_url": urls["model_url"],
            "result_put_url": urls["result_put_url"],
            "result_url": urls["result_url"],
            "options": options or {},
        }
    }
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
      {job_id, status, progress, message, result_url, error}
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
