"""
RunPod Serverless Handler – Football Analyzer
Input:  {
    "video_url":      "https://...presigned...",   # pre-signed GET URL del video
    "model_url":      "https://...presigned...",   # pre-signed GET URL del modello
    "result_put_url": "https://...presigned...",   # pre-signed PUT URL per i risultati
    "result_url":     "https://...public...",      # URL pubblico risultato (passato dal client)
    "options": {}
}
Output: {"status": "completed", "result_url": "https://...", "summary": {...}}
"""
import json
import logging
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

import runpod

# Aggiungi /app al path per importare i moduli locali
sys.path.insert(0, "/app")

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

MODEL_PATH = Path("/app/models/best_ckpt.pth")


def _ensure_model(model_url: str = None):
    """Scarica best_ckpt.pth. Usa model_url (pre-signed) se disponibile,
    altrimenti tenta boto3 da env vars come fallback."""
    if MODEL_PATH.exists():
        LOG.info("Model already present: %.1f MB", MODEL_PATH.stat().st_size / 1e6)
        return
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    if model_url:
        LOG.info("Downloading model via pre-signed URL...")
        urllib.request.urlretrieve(model_url, str(MODEL_PATH))
        LOG.info("Model downloaded: %.1f MB", MODEL_PATH.stat().st_size / 1e6)
        return

    # Fallback: boto3 con credenziali da env vars
    LOG.info("Downloading model from R2 via boto3 (fallback)...")
    import boto3
    endpoint = os.environ["R2_ENDPOINT_URL"]
    access_key = os.environ["R2_ACCESS_KEY_ID"]
    secret_key = os.environ["R2_SECRET_ACCESS_KEY"]
    bucket = os.environ.get("R2_BUCKET_NAME", "match-analysis-videos")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )
    client.download_file(bucket, "models/best_ckpt.pth", str(MODEL_PATH))
    LOG.info("Model downloaded: %.1f MB", MODEL_PATH.stat().st_size / 1e6)


def _upload_result_presigned(local_path: str, put_url: str):
    """Carica JSON risultato via pre-signed PUT URL (nessuna credenziale richiesta)."""
    import urllib.request
    with open(local_path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        put_url,
        data=data,
        method="PUT",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        if resp.status not in (200, 204):
            raise Exception(f"Upload risultato fallito: HTTP {resp.status}")
    LOG.info("Risultato caricato via pre-signed PUT URL")


def _upload_result_boto3(local_path: str, remote_key: str) -> str:
    """Fallback: carica JSON risultato su R2 via boto3."""
    import boto3
    endpoint = os.environ["R2_ENDPOINT_URL"]
    access_key = os.environ["R2_ACCESS_KEY_ID"]
    secret_key = os.environ["R2_SECRET_ACCESS_KEY"]
    bucket = os.environ.get("R2_BUCKET_NAME", "match-analysis-videos")
    public_base = os.environ.get("R2_PUBLIC_URL", "").rstrip("/")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )
    client.upload_file(
        local_path, bucket, remote_key,
        ExtraArgs={"ContentType": "application/json"},
    )
    return f"{public_base}/{remote_key}"


def handler(job):
    """Handler principale RunPod Serverless."""
    job_input = job.get("input", {})
    video_url = job_input.get("video_url")
    model_url = job_input.get("model_url")          # pre-signed GET URL modello
    result_put_url = job_input.get("result_put_url")  # pre-signed PUT URL risultato
    result_url_out = job_input.get("result_url")      # URL pubblico risultato (da restituire)
    options = job_input.get("options", {})

    if not video_url:
        return {"error": "video_url è richiesto"}

    # Assicura che il modello sia presente
    try:
        _ensure_model(model_url)
    except Exception as e:
        return {"error": f"Download modello fallito: {e}"}

    tmp_video = None
    tmp_result = None
    try:
        # Scarica video in file temporaneo
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            tmp_video = f.name
        LOG.info("Downloading video from %s ...", video_url[:80])
        urllib.request.urlretrieve(video_url, tmp_video)
        LOG.info("Video downloaded: %.1f MB", Path(tmp_video).stat().st_size / 1e6)

        # File output detections
        tmp_result = tmp_video.replace(".mp4", "_detections.json")

        # Importa e lancia detection
        from analysis.player_detection import run_player_detection

        conf_thresh = float(options.get("conf_thresh", 0.3))
        target_fps = float(options.get("target_fps", 10.0))

        LOG.info("Starting player detection (conf=%.2f, fps=%.1f)...", conf_thresh, target_fps)
        success, err = run_player_detection(
            video_path=tmp_video,
            output_path=tmp_result,
            conf_thresh=conf_thresh,
            classify_teams=True,
            target_fps=target_fps,
        )

        if not success:
            return {"error": f"Detection fallita: {err}"}

        # Esegui tracking (aggiunge track_id stabile per ogni giocatore)
        tmp_tracks = tmp_video.replace(".mp4", "_tracks.json")
        LOG.info("Starting player tracking...")
        from analysis.player_tracking import run_player_tracking
        tracking_ok = run_player_tracking(
            detections_path=tmp_result,
            output_path=tmp_tracks,
            max_age=30,
            iou_thresh=0.3,
        )
        # Usa tracks se disponibili, altrimenti fallback su detections
        result_file = tmp_tracks if tracking_ok and Path(tmp_tracks).exists() else tmp_result
        LOG.info("Using result file: %s", result_file)

        # Leggi risultati finali
        with open(result_file, "r", encoding="utf-8") as f:
            result_data = json.load(f)

        # Calcola sommario
        n_frames = len(result_data.get("frames", []))
        all_dets = [d for fr in result_data["frames"] for d in fr.get("detections", [])]
        n_players = sum(1 for d in all_dets if d.get("role") in ("player", "goalie"))
        n_balls = sum(1 for d in all_dets if d.get("role") == "ball")
        n_tracks = len(result_data.get("tracks", {}))

        # Carica risultato su R2
        LOG.info("Uploading results (%d frames, %d tracks)...", n_frames, n_tracks)
        if result_put_url:
            _upload_result_presigned(result_file, result_put_url)
            result_url = result_url_out or "uploaded"
        else:
            # Fallback: boto3 con env vars
            video_name = Path(video_url.split("?")[0]).stem  # rimuovi query string pre-signed
            result_key = f"results/{video_name}_tracks.json"
            result_url = _upload_result_boto3(result_file, result_key)
        LOG.info("Results uploaded: %s", result_url)

        return {
            "status": "completed",
            "result_url": result_url,
            "summary": {
                "frames_analyzed": n_frames,
                "total_player_detections": n_players,
                "total_ball_detections": n_balls,
                "unique_tracks": n_tracks,
                "video_fps": result_data.get("fps", 0),
                "width": result_data.get("width", 0),
                "height": result_data.get("height", 0),
            },
        }

    except Exception as e:
        LOG.exception("Handler error")
        return {"error": str(e)}

    finally:
        tmp_tracks_local = locals().get("tmp_tracks")
        for p in [tmp_video, tmp_result, tmp_tracks_local]:
            if p and Path(p).exists():
                try:
                    Path(p).unlink()
                except Exception:
                    pass


# Avvia il serverless worker
runpod.serverless.start({"handler": handler})
