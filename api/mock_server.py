"""
Server API mock per test client Fase 4: POST job, SSE eventi, GET status/result.
Avvio: pip install flask && python -m api.mock_server
Poi avvia il client con FOOTBALL_ANALYZER_API_URL=http://127.0.0.1:5000
"""
from __future__ import annotations

import json
import time
import uuid
from threading import Thread

try:
    from flask import Flask, request, Response, jsonify
except ImportError:
    print("Installa Flask: pip install flask")
    raise

app = Flask(__name__)

# In memoria: job_id -> stato (per polling e result stub)
_jobs = {}
# Lock semplificato (single-threaded Flask dev server)
_jobs_lock = None


def _job_status(job_id: str) -> dict:
    return _jobs.get(
        job_id,
        {"job_id": job_id, "status": "pending", "progress": 0, "message": "In coda", "result_url": None},
    )


def _set_job(job_id: str, status: str, progress: int = 0, message: str = ""):
    _jobs[job_id] = {
        "job_id": job_id,
        "status": status,
        "progress": progress,
        "message": message,
        "result_url": None,
    }


@app.route("/v1/jobs", methods=["POST"])
def create_job():
    if "video" not in request.files and not request.json:
        return jsonify({"error": "video o video_url richiesto"}), 400
    job_id = str(uuid.uuid4())
    _set_job(job_id, "pending", 0, "Job creato")
    return jsonify({"job_id": job_id, "status": "pending", "message": "Job creato"}), 201


@app.route("/v1/jobs/<job_id>/status", methods=["GET"])
def get_status(job_id):
    st = _job_status(job_id)
    return jsonify(st)


@app.route("/v1/jobs/<job_id>/result", methods=["GET"])
def get_result(job_id):
    st = _job_status(job_id)
    if st.get("status") != "completed":
        return jsonify({"error": "Risultato non ancora disponibile"}), 202
    # Stub risultato minimo (schema Step 0.1)
    return jsonify({
        "version": "1.0",
        "source": "cloud",
        "project_id": None,
        "calibration": None,
        "parameters_used": {"fps": 10, "target_fps": 10, "preprocess": False, "mode": "full"},
        "tracking": {"player_tracks": {}, "ball_tracks": {}},
        "events": {"manual": [], "automatic": []},
        "metrics": {"players": [], "teams": []},
        "clips": [],
        "heatmaps": {},
    })


def _sse_stream(job_id: str):
    """Genera eventi SSE: dopo 2s running, dopo 5s completed."""
    _set_job(job_id, "running", 10, "Avvio analisi...")
    yield f"data: {json.dumps(_job_status(job_id))}\n\n"
    time.sleep(2)
    _set_job(job_id, "running", 50, "Fase 2/6 – Player detection")
    yield f"data: {json.dumps(_job_status(job_id))}\n\n"
    time.sleep(2)
    _set_job(job_id, "completed", 100, "Completato")
    yield f"data: {json.dumps(_job_status(job_id))}\n\n"


@app.route("/v1/jobs/events", methods=["GET"])
def job_events():
    job_id = request.args.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id richiesto"}), 400
    _set_job(job_id, "pending", 0, "Job creato")
    return Response(
        _sse_stream(job_id),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    print("Mock API: http://127.0.0.1:5000")
    print("Client: FOOTBALL_ANALYZER_API_URL=http://127.0.0.1:5000 python main_web.py")
    app.run(host="127.0.0.1", port=5000, threaded=True)
