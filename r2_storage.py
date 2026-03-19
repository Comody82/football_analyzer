"""
Cloudflare R2 storage client.
Upload video → ottieni URL pubblico per RunPod.
Credenziali da .env (R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, ecc.)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Callable

LOG = logging.getLogger(__name__)


def _load_env():
    """Carica .env se presente."""
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass


def _get_r2_client():
    """Crea client boto3 per R2."""
    import boto3
    _load_env()
    endpoint = os.environ.get("R2_ENDPOINT_URL")
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not all([endpoint, access_key, secret_key]):
        raise ValueError("Credenziali R2 mancanti nel file .env")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )


def upload_video(
    local_path: str,
    remote_key: str | None = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    Carica video su R2. Ritorna (public_url, None) o (None, errore).
    remote_key: nome file su R2 (default: nome file locale).
    progress_callback(bytes_trasferiti, bytes_totali).
    """
    _load_env()
    bucket = os.environ.get("R2_BUCKET_NAME", "match-analysis-videos")
    public_base = os.environ.get("R2_PUBLIC_URL", "").rstrip("/")

    path = Path(local_path)
    if not path.exists():
        return None, f"File non trovato: {local_path}"

    if remote_key is None:
        remote_key = path.name

    file_size = path.stat().st_size

    try:
        client = _get_r2_client()

        if progress_callback and file_size > 0:
            uploaded = [0]
            def _cb(bytes_amount):
                uploaded[0] += bytes_amount
                progress_callback(uploaded[0], file_size)
            client.upload_file(
                str(path), bucket, remote_key,
                Callback=_cb,
                ExtraArgs={"ContentType": "video/mp4"},
            )
        else:
            client.upload_file(
                str(path), bucket, remote_key,
                ExtraArgs={"ContentType": "video/mp4"},
            )

        if public_base:
            url = f"{public_base}/{remote_key}"
        else:
            url = f"https://{bucket}.r2.dev/{remote_key}"

        LOG.info("Uploaded %s → %s", local_path, url)
        return url, None

    except Exception as e:
        LOG.error("R2 upload failed: %s", e)
        return None, str(e)


def delete_video(remote_key: str) -> Optional[str]:
    """Elimina file da R2. Ritorna None se ok, stringa errore altrimenti."""
    _load_env()
    bucket = os.environ.get("R2_BUCKET_NAME", "match-analysis-videos")
    try:
        client = _get_r2_client()
        client.delete_object(Bucket=bucket, Key=remote_key)
        return None
    except Exception as e:
        LOG.warning("R2 delete failed: %s", e)
        return str(e)
