"""
Test flusso cloud: mock server + cloud_client (upload -> SSE -> result).
Esegui con mock server già avviato: python -m api.mock_server
"""
import os
import sys
import tempfile

# progetto root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cloud_client import create_job, get_result, run_sse_stream

BASE = os.environ.get("FOOTBALL_ANALYZER_API_URL", "http://127.0.0.1:5000")


def main():
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"\x00\x00")
        video_path = f.name
    try:
        job_id, err = create_job(BASE, video_path, {"mode": "full", "target_fps": 10})
        assert not err, f"create_job failed: {err}"
        assert job_id, "no job_id"
        print(f"OK job_id={job_id}")

        events = []
        def on_ev(ev):
            events.append(ev)
            print(f"  event: {ev.get('status')} {ev.get('message', '')}")

        done = run_sse_stream(BASE, job_id, on_ev)
        assert done, "SSE stream did not complete with completed/failed"
        assert any(e.get("status") == "completed" for e in events), "no completed event"
        print("OK SSE completed")

        result, err = get_result(BASE, job_id)
        assert not err, f"get_result failed: {err}"
        assert result is not None, "no result"
        assert result.get("version") == "1.0", "bad version"
        assert result.get("source") == "cloud", "bad source"
        assert "tracking" in result, "missing tracking"
        print("OK result loaded")
        print("Cloud flow test passed.")
    finally:
        os.unlink(video_path)


if __name__ == "__main__":
    main()
