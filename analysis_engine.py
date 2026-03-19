#!/usr/bin/env python3
"""
Analysis Engine - Motore di analisi in processo separato.

Esegue player detection, player tracking, ball detection, ball tracking
su video di partite. Può essere lanciato da Football Analyzer (Qt) o da CLI.

Uso:
  python analysis_engine.py --video path/to/video.mp4 --output path/to/project_analysis_dir --mode full
  python analysis_engine.py --video video.mp4 --output ./out --mode player
  python analysis_engine.py --video video.mp4 --output ./out --mode ball

Output: progress.json e finished.json nella cartella output per monitoraggio.
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Aggiungi la root del progetto al path
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))


def _set_low_priority():
    """Imposta priorità bassa del processo (PC utilizzabile durante analisi)."""
    try:
        import psutil
        p = psutil.Process(os.getpid())
        try:
            if sys.platform == "win32" and hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS"):
                p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            elif hasattr(p, "nice"):
                p.nice(10)  # Unix: 10 = below normal
        except (psutil.AccessDenied, AttributeError, ValueError):
            pass
    except ImportError:
        pass


def _write_progress(output_dir: Path, phase: str, current: int, total: int, msg: str = ""):
    """Scrive progress.json per monitoraggio esterno."""
    data = {
        "phase": phase,
        "current_frame": current,
        "total_frames": total,
        "pct": int(100 * current / total) if total > 0 else 0,
        "message": msg or f"{phase}: {current}/{total}",
    }
    p = output_dir / "progress.json"
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def _write_finished(output_dir: Path, success: bool, outputs: list, error_msg: str = ""):
    """Scrive finished.json al termine."""
    data = {
        "success": success,
        "outputs": outputs,
        "error": error_msg,
    }
    p = output_dir / "finished.json"
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def _find_latest_checkpoint(output_path: Path) -> tuple[int, dict] | None:
    """
    Trova l'ultimo checkpoint per output_path (es. .../player_detections.json).
    Ritorna (start_frame, results) dove start_frame è il primo frame da processare,
    o None se nessun checkpoint valido.
    """
    import re
    parent = Path(output_path).parent
    stem = Path(output_path).stem
    matches = list(parent.glob(f"{stem}_checkpoint_*.json"))
    if not matches:
        return None
    frame_nums = []
    for m in matches:
        mobj = re.search(r"_checkpoint_(\d+)\.json$", m.name)
        if mobj:
            frame_nums.append((int(mobj.group(1)), m))
    if not frame_nums:
        return None
    _, best_path = max(frame_nums, key=lambda x: x[0])
    try:
        with open(best_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    frames = data.get("frames", [])
    if not frames:
        return None
    last_frame = frames[-1].get("frame", -1)
    return (last_frame + 1, data)


def _run_player_pipeline(
    video_path: str,
    output_dir: Path,
    fps: float,
    calibration_path: str,
    checkpoint_interval: int,
    first_checkpoint: int,
    resume: bool = False,
) -> tuple[bool, str]:
    """Esegue player detection + player tracking."""
    from analysis.player_detection import run_player_detection, get_detections_path
    from analysis.player_tracking import run_player_tracking, get_tracks_path

    project_dir = str(output_dir.parent)
    detections_path = Path(get_detections_path(project_dir))
    tracks_path = str(get_tracks_path(project_dir))

    start_frame = 0
    initial_results = None
    if resume and checkpoint_interval > 0:
        ckpt = _find_latest_checkpoint(detections_path)
        if ckpt:
            start_frame, initial_results = ckpt

    def on_progress(cur: int, total: int, msg: str):
        _write_progress(output_dir, "player_detection", cur, total, msg)

    ok, err_msg = run_player_detection(
        video_path,
        str(detections_path),
        conf_thresh=0.20,
        classify_teams=True,
        progress_callback=on_progress,
        target_fps=fps,
        calibration_path=calibration_path,
        checkpoint_interval=checkpoint_interval,
        first_checkpoint=first_checkpoint,
        start_frame=start_frame,
        initial_results=initial_results,
    )
    if not ok:
        return False, err_msg or "Player detection fallita."

    def on_progress_trk(cur: int, total: int, msg: str):
        _write_progress(output_dir, "player_tracking", cur, total, msg)

    ok = run_player_tracking(
        detections_path,
        tracks_path,
        progress_callback=on_progress_trk,
    )
    if not ok:
        return False, "Player tracking fallito."
    return True, ""


def _run_ball_pipeline(
    video_path: str,
    output_dir: Path,
    fps: float,
    calibration_path: str,
    checkpoint_interval: int,
    first_checkpoint: int,
    resume: bool = False,
) -> tuple[bool, str]:
    """Esegue ball detection + ball tracking."""
    from analysis.ball_detection import run_ball_detection, get_ball_detections_path, _get_yolox_predictor
    from analysis.ball_tracking import run_ball_tracking, get_ball_tracks_path

    project_dir = str(output_dir.parent)
    detections_path = Path(get_ball_detections_path(project_dir))
    tracks_path = str(get_ball_tracks_path(project_dir))

    predictor, err = _get_yolox_predictor()
    if predictor is None:
        return False, err or "YOLOX non inizializzato."

    start_frame = 0
    initial_results = None
    if resume and checkpoint_interval > 0:
        ckpt = _find_latest_checkpoint(detections_path)
        if ckpt:
            start_frame, initial_results = ckpt

    def on_progress(cur: int, total: int, msg: str):
        _write_progress(output_dir, "ball_detection", cur, total, msg)

    ok, err_msg = run_ball_detection(
        video_path,
        str(detections_path),
        conf_thresh=0.12,
        progress_callback=on_progress,
        predictor=predictor,
        target_fps=fps,
        calibration_path=calibration_path,
        checkpoint_interval=checkpoint_interval,
        first_checkpoint=first_checkpoint,
        start_frame=start_frame,
        initial_results=initial_results,
    )
    if not ok:
        return False, err_msg or "Ball detection fallita."

    def on_progress_trk(cur: int, total: int, msg: str):
        _write_progress(output_dir, "ball_tracking", cur, total, msg)

    ok = run_ball_tracking(
        detections_path,
        tracks_path,
        progress_callback=on_progress_trk,
    )
    if not ok:
        return False, "Ball tracking fallito."
    return True, ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Football Analyzer - Motore analisi (player/ball detection + tracking)"
    )
    parser.add_argument("--video", required=True, help="Path al video")
    parser.add_argument("--output", required=True, help="Directory output analisi (project_analysis_dir)")
    parser.add_argument(
        "--mode",
        choices=["player", "ball", "full"],
        default="full",
        help="Modalità: player, ball, full (default: full)",
    )
    parser.add_argument("--fps", type=float, default=10.0, help="FPS target per sampling (default: 10)")
    parser.add_argument("--crop", action="store_true", help="Usa field crop se calibration presente")
    parser.add_argument("--checkpoint-interval", type=int, default=1000, help="Salva checkpoint ogni N frame dopo il primo (0=off, default: 1000)")
    parser.add_argument("--checkpoint-first", type=int, default=500, help="Primo checkpoint a N frame (default: 500)")
    parser.add_argument("--resume", action="store_true", help="Riprende da ultimo checkpoint se presente")
    parser.add_argument("--run-preprocess", action="store_true", help="Esegue preprocessing video (720p) prima dell'analisi se assente")
    parser.add_argument("--no-priority", action="store_true", help="Non impostare priorità bassa")

    args = parser.parse_args()
    video_path = str(Path(args.video).resolve())
    output_base = Path(args.output).resolve()

    if not Path(video_path).exists():
        print(f"Errore: video non trovato: {video_path}", file=sys.stderr)
        return 1

    # Directory output: project_analysis_dir contiene analysis_output
    # get_detections_path(project_dir) usa project_dir = output_base
    analysis_output = output_base / "analysis_output"
    analysis_output.mkdir(parents=True, exist_ok=True)

    calibration_path = None
    if args.crop:
        cal = analysis_output / "field_calibration.json"
        if cal.exists():
            calibration_path = str(cal)

    checkpoint = args.checkpoint_interval if args.checkpoint_interval > 0 else 0
    first_checkpoint = args.checkpoint_first if checkpoint > 0 else 0

    if not args.no_priority:
        _set_low_priority()

    _write_progress(analysis_output, "start", 0, 1, "Avvio analisi...")

    # Video input: preprocessato se esiste (o se --run-preprocess)
    from analysis.video_preprocessing import get_preprocessed_path, preprocess_video
    preprocessed = get_preprocessed_path(str(output_base))
    if args.run_preprocess and not preprocessed.exists():
        _write_progress(analysis_output, "preprocess", 0, 100, "Preprocessing video...")
        def _on_preprocess(c, t, msg):
            _write_progress(analysis_output, "preprocess", c, t, msg or f"Frame {c}/{t}")
        if not preprocess_video(video_path, str(preprocessed), progress_callback=_on_preprocess):
            _write_finished(analysis_output, False, [], "Preprocessing fallito.")
            return 1
        _write_progress(analysis_output, "preprocess", 100, 100, "Preprocessing completato")
    video_input = str(preprocessed) if preprocessed.exists() else video_path

    outputs = []
    error_msg = ""

    try:
        if args.mode in ("player", "full"):
            ok, err = _run_player_pipeline(
                video_input, analysis_output, args.fps, calibration_path, checkpoint, first_checkpoint, resume=args.resume
            )
            if not ok:
                _write_finished(analysis_output, False, outputs, err)
                print(err, file=sys.stderr)
                return 1
            outputs.extend(["player_detections.json", "player_tracks.json"])

        if args.mode in ("ball", "full"):
            ok, err = _run_ball_pipeline(
                video_input, analysis_output, args.fps, calibration_path, checkpoint, first_checkpoint, resume=args.resume
            )
            if not ok:
                _write_finished(analysis_output, False, outputs, err)
                print(err, file=sys.stderr)
                return 1
            outputs.extend(["ball_detections.json", "ball_tracks.json"])

        # Clustering globale squadre (sovrascrive team in player_tracks)
        if args.mode in ("player", "full"):
            from analysis.global_team_clustering import run_global_team_clustering
            def _on_cluster(c, t, msg):
                _write_progress(analysis_output, "global_team_clustering", c, max(1, t), msg or "Clustering globale squadre...")
            if not run_global_team_clustering(str(output_base), progress_callback=_on_cluster):
                _write_finished(analysis_output, False, outputs, "Clustering globale fallito.")
                return 1

        # Event engine (Fase 6): possesso, passaggio, recupero, tiro, pressing
        if args.mode == "full":
            from analysis.event_engine import run_event_engine_from_project
            def _on_events(c, t, msg):
                _write_progress(analysis_output, "event_engine", c, max(1, t), msg or "Event engine...")
            if not run_event_engine_from_project(str(output_base), args.fps, progress_callback=_on_events):
                _write_finished(analysis_output, False, outputs, "Event engine fallito.")
                return 1
            outputs.append("detections/events_engine.json")

            # Metriche automatiche (Fase 7): per giocatore e per squadra
            from analysis.metrics import run_metrics_from_project
            def _on_metrics(c, t, msg):
                _write_progress(analysis_output, "metrics", c, max(1, t), msg or "Metriche...")
            if not run_metrics_from_project(str(output_base), args.fps, progress_callback=_on_metrics):
                _write_finished(analysis_output, False, outputs, "Metriche fallite.")
                return 1
            outputs.append("metrics.json")

        _write_progress(analysis_output, "done", 1, 1, "Completato")
        _write_finished(analysis_output, True, outputs, "")
        return 0

    except Exception as e:
        error_msg = str(e)
        _write_finished(analysis_output, False, outputs, error_msg)
        print(f"Errore: {error_msg}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
