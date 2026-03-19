"""
RunPod Serverless Handler – Football Analyzer
Input:  {"video_url": "https://...", "options": {}}
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

MODEL_URL = os.environ.get(
    "MODEL_URL",
    "https://pub-0dbac19cd9a943ff8d0baff780d52297.r2.dev/models/best_ckpt.pth",
)
MODEL_PATH = Path("/app/models/best_ckpt.pth")


def _ensure_model():
    """Scarica best_ckpt.pth da R2 via boto3 (credenziali da env vars)."""
    if MODEL_PATH.exists():
        LOG.info("Model already present: %.1f MB", MODEL_PATH.stat().st_size / 1e6)
        return
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG.info("Downloading model from R2 via boto3...")
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


def _upload_result(local_path: str, remote_key: str) -> str:
    """Carica JSON risultato su R2 e ritorna URL pubblico."""
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
    options = job_input.get("options", {})

    if not video_url:
        return {"error": "video_url è richiesto"}

    # Assicura che il modello sia presente
    try:
        _ensure_model()
    except Exception as e:
        return {"error": f"Download modello fallito: {e}"}

    tmp_video = None
    tmp_result = None
    try:
        # Scarica video in file temporaneo
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            tmp_video = f.name
        LOG.info("Downloading video from %s ...", video_url)
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

        # Leggi risultati
        with open(tmp_result, "r", encoding="utf-8") as f:
            detections = json.load(f)

        # Calcola sommario
        n_frames = len(detections.get("frames", []))
        all_dets = [d for fr in detections["frames"] for d in fr.get("detections", [])]
        n_players = sum(1 for d in all_dets if d.get("role") in ("player", "goalie"))
        n_balls = sum(1 for d in all_dets if d.get("role") == "ball")

        # Carica risultato su R2
        video_name = Path(video_url).stem
        result_key = f"results/{video_name}_detections.json"
        LOG.info("Uploading results to R2 (%d frames)...", n_frames)
        result_url = _upload_result(tmp_result, result_key)
        LOG.info("Results uploaded: %s", result_url)

        return {
            "status": "completed",
            "result_url": result_url,
            "summary": {
                "frames_analyzed": n_frames,
                "total_player_detections": n_players,
                "total_ball_detections": n_balls,
                "video_fps": detections.get("fps", 0),
                "width": detections.get("width", 0),
                "height": detections.get("height", 0),
            },
        }

    except Exception as e:
        LOG.exception("Handler error")
        return {"error": str(e)}

    finally:
        for p in [tmp_video, tmp_result]:
            if p and Path(p).exists():
                try:
                    Path(p).unlink()
                except Exception:
                    pass


# Avvia il serverless worker
runpod.serverless.start({"handler": handler})
