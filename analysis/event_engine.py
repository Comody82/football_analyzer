"""
Event engine (Fase 6): possesso, passaggio, recupero, tiro, pressing.
Eseguito dopo ball tracking e clustering globale; usa soglie da event_engine_params.
Output in formato schema Step 0.1 (events.automatic).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .event_engine_params import get_params
from .homography import get_calibrator


def _ball_center(det: Optional[Dict]) -> Optional[Tuple[float, float]]:
    if not det or "x" not in det:
        return None
    x, y = det["x"], det["y"]
    w, h = det.get("w", 0), det.get("h", 0)
    return (x + w / 2, y + h / 2)


def _player_center(d: Dict) -> Tuple[float, float]:
    x, y = d["x"], d["y"]
    w, h = d.get("w", 0), d.get("h", 0)
    return (x + w / 2, y + h / 2)


def _dist_m(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def _build_frame_data(
    player_tracks: Dict,
    ball_tracks: Dict,
    calibrator: Optional[Any],
    width: int,
    height: int,
    field_length_m: float,
    field_width_m: float,
) -> Tuple[Dict[int, Tuple[float, float]], Dict[int, List[Tuple[int, int, float, float]]], float]:
    """
    Restituisce:
    - ball_by_frame: frame_idx -> (x_m, y_m) o (x_px, y_px) se no calibrazione
    - players_by_frame: frame_idx -> [(track_id, team, x_m, y_m), ...]
    - scale: metri per pixel (se no calibrazione, approssimazione da dimensioni campo/video)
    """
    ball_by_frame: Dict[int, Tuple[float, float]] = {}
    players_by_frame: Dict[int, List[Tuple[int, int, float, float]]] = {}
    scale = field_length_m / width if width else 0.05  # fallback

    pt_frames = {f["frame"]: f for f in player_tracks.get("frames", [])}
    bt_frames = {f["frame"]: f for f in ball_tracks.get("frames", [])}
    all_frames = sorted(set(pt_frames.keys()) | set(bt_frames.keys()))

    for frame_idx in all_frames:
        # Palla
        bt = bt_frames.get(frame_idx, {})
        det = bt.get("detection") if isinstance(bt.get("detection"), dict) else None
        bc = _ball_center(det)
        if bc:
            px, py = bc
            if calibrator:
                pt_m = calibrator.pixel_to_field(px, py)
                if pt_m:
                    ball_by_frame[frame_idx] = pt_m
                else:
                    ball_by_frame[frame_idx] = (px * scale, py * scale)
            else:
                ball_by_frame[frame_idx] = (px * scale, py * scale)

        # Giocatori
        pt = pt_frames.get(frame_idx, {})
        dets = pt.get("detections", [])
        players_by_frame[frame_idx] = []
        for d in dets:
            tid = d.get("track_id", -1)
            team = d.get("team", -1)
            cx, cy = _player_center(d)
            if calibrator:
                pt_m = calibrator.pixel_to_field(cx, cy)
                if pt_m:
                    players_by_frame[frame_idx].append((tid, team, pt_m[0], pt_m[1]))
                else:
                    players_by_frame[frame_idx].append((tid, team, cx * scale, cy * scale))
            else:
                players_by_frame[frame_idx].append((tid, team, cx * scale, cy * scale))

    return ball_by_frame, players_by_frame, scale


def _compute_possession(
    ball_by_frame: Dict[int, Tuple[float, float]],
    players_by_frame: Dict[int, List[Tuple[int, int, float, float]]],
    max_dist_m: float,
    min_frames: int,
    fps: float,
) -> Tuple[List[Dict], Dict[int, Tuple[Optional[int], Optional[int]]]]:
    """
    Per ogni frame: giocatore più vicino alla palla sotto soglia -> possesso.
    Ritorna: (segmenti [{start_frame, end_frame, team, track_id}], possession_by_frame: frame -> (track_id, team))
    """
    frames_sorted = sorted(set(ball_by_frame.keys()) & set(players_by_frame.keys()))
    possession_by_frame: Dict[int, Tuple[Optional[int], Optional[int]]] = {}
    for frame_idx in frames_sorted:
        ball_pt = ball_by_frame.get(frame_idx)
        players = players_by_frame.get(frame_idx, [])
        if not ball_pt or not players:
            possession_by_frame[frame_idx] = (None, None)
            continue
        bx, by = ball_pt
        best_dist = max_dist_m + 1
        best_tid: Optional[int] = None
        best_team: Optional[int] = None
        for tid, team, px, py in players:
            d = _dist_m(bx, by, px, py)
            if d < best_dist:
                best_dist = d
                best_tid = tid
                best_team = team
        if best_dist <= max_dist_m:
            possession_by_frame[frame_idx] = (best_tid, best_team)
        else:
            possession_by_frame[frame_idx] = (None, None)

    # Segmenti continui (stesso team/track_id) con durata >= min_frames
    segments: List[Dict] = []
    i = 0
    while i < len(frames_sorted):
        frame_idx = frames_sorted[i]
        tid, team = possession_by_frame.get(frame_idx, (None, None))
        if tid is None:
            i += 1
            continue
        start_frame = frame_idx
        end_frame = frame_idx
        j = i + 1
        while j < len(frames_sorted) and frames_sorted[j] == end_frame + 1:
            f = frames_sorted[j]
            t, te = possession_by_frame.get(f, (None, None))
            if t != tid or te != team:
                break
            end_frame = f
            j += 1
        if end_frame - start_frame + 1 >= min_frames:
            segments.append({
                "start_frame": start_frame,
                "end_frame": end_frame,
                "team": team,
                "track_id": tid,
            })
        i = j
    return segments, possession_by_frame


def _detect_passes(
    possession_by_frame: Dict[int, Tuple[Optional[int], Optional[int]]],
    ball_by_frame: Dict[int, Tuple[float, float]],
    params: Dict,
    fps: float,
) -> List[Dict]:
    """Passaggio: cambio possesso da A a B stesso team con spostamento palla."""
    pass_events = []
    frames_sorted = sorted(set(possession_by_frame.keys()) & set(ball_by_frame.keys()))
    for i in range(1, len(frames_sorted)):
        prev_frame, curr_frame = frames_sorted[i - 1], frames_sorted[i]
        if curr_frame != prev_frame + 1:
            continue
        prev_tid, prev_team = possession_by_frame.get(prev_frame, (None, None))
        curr_tid, curr_team = possession_by_frame.get(curr_frame, (None, None))
        if prev_tid is None or curr_tid is None or prev_team is None or curr_team is None:
            continue
        if prev_team != curr_team:
            continue
        if prev_tid == curr_tid:
            continue
        b_prev = ball_by_frame.get(prev_frame)
        b_curr = ball_by_frame.get(curr_frame)
        if not b_prev or not b_curr:
            continue
        dist_ball = _dist_m(b_prev[0], b_prev[1], b_curr[0], b_curr[1])
        if dist_ball < 0.5:
            continue
        ts_ms = int(curr_frame * 1000 / fps) if fps else 0
        pass_events.append({
            "type": "pass",
            "timestamp_ms": ts_ms,
            "end_ms": None,
            "team": curr_team,
            "track_id": prev_tid,
            "track_id_to": curr_tid,
            "zone": None,
        })
    return pass_events


def _in_defensive_zone(x_m: float, params: Dict) -> bool:
    x0, x1 = params.get("defensive_area_x_min_m", 0), params.get("defensive_area_x_max_m", 17)
    x2, x3 = params.get("defensive_area_x_max_other_side_m", 88), params.get("defensive_area_x_min_other_side_m", 105)
    return (x0 <= x_m <= x1) or (x2 <= x_m <= x3)


def _detect_recoveries(
    possession_by_frame: Dict[int, Tuple[Optional[int], Optional[int]]],
    ball_by_frame: Dict[int, Tuple[float, float]],
    params: Dict,
    fps: float,
) -> List[Dict]:
    """Recupero: cambio possesso in area difensiva."""
    recovery_events = []
    frames_sorted = sorted(set(possession_by_frame.keys()) & set(ball_by_frame.keys()))
    for i in range(1, len(frames_sorted)):
        prev_frame, curr_frame = frames_sorted[i - 1], frames_sorted[i]
        if curr_frame != prev_frame + 1:
            continue
        prev_tid, prev_team = possession_by_frame.get(prev_frame, (None, None))
        curr_tid, curr_team = possession_by_frame.get(curr_frame, (None, None))
        if prev_team is None and curr_team is None:
            continue
        if prev_team == curr_team:
            continue
        b_curr = ball_by_frame.get(curr_frame)
        if not b_curr:
            continue
        x_m = b_curr[0]
        if not _in_defensive_zone(x_m, params):
            continue
        ts_ms = int(curr_frame * 1000 / fps) if fps else 0
        zone = "left" if x_m < 52.5 else "right"
        recovery_events.append({
            "type": "recovery",
            "timestamp_ms": ts_ms,
            "end_ms": None,
            "team": curr_team,
            "track_id": curr_tid,
            "track_id_to": None,
            "zone": zone,
        })
    return recovery_events


def _detect_shots(
    ball_by_frame: Dict[int, Tuple[float, float]],
    params: Dict,
    fps: float,
) -> List[Dict]:
    """Tiro: velocità palla oltre soglia + direzione verso porta. Un solo evento per 'burst' (debounce)."""
    shot_events = []
    min_speed = params.get("min_ball_speed_m_s", 5.0)
    goal_lx = params.get("goal_left_x_m", 0)
    goal_rx = params.get("goal_right_x_m", 105)
    goal_cy = params.get("goal_center_y_m", 34)
    max_angle_deg = params.get("max_angle_deg_from_goal", 45)
    # Intervallo minimo tra due eventi "tiro" (ms) per evitare decine di falsi positivi su stesso movimento
    min_interval_ms = params.get("min_shot_interval_ms", 1500)
    dt_s = 1.0 / fps if fps else 0.1
    frames_sorted = sorted(ball_by_frame.keys())
    last_shot_ts_ms: Optional[int] = None
    for j in range(1, len(frames_sorted)):
        f0, f1 = frames_sorted[j - 1], frames_sorted[j]
        if f1 - f0 != 1:
            continue
        p0 = ball_by_frame[f0]
        p1 = ball_by_frame[f1]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        speed = math.hypot(dx, dy) / dt_s
        if speed < min_speed:
            continue
        # Direzione verso porta sinistra (x=0) o destra (x=105)
        to_goal_left = math.atan2(goal_lx - p1[0], goal_cy - p1[1])
        to_goal_right = math.atan2(goal_rx - p1[0], goal_cy - p1[1])
        move_angle = math.atan2(dx, dy)
        angle_deg_left = abs(math.degrees(move_angle - to_goal_left)) % 360
        angle_deg_right = abs(math.degrees(move_angle - to_goal_right)) % 360
        if angle_deg_left > 180:
            angle_deg_left = 360 - angle_deg_left
        if angle_deg_right > 180:
            angle_deg_right = 360 - angle_deg_right
        if angle_deg_left > max_angle_deg and angle_deg_right > max_angle_deg:
            continue
        ts_ms = int(f1 * 1000 / fps) if fps else 0
        if last_shot_ts_ms is not None and (ts_ms - last_shot_ts_ms) < min_interval_ms:
            continue
        last_shot_ts_ms = ts_ms
        team = 0 if dx < 0 else 1  # approssimazione: direzione verso x=0 -> team 0
        shot_events.append({
            "type": "shot",
            "timestamp_ms": ts_ms,
            "end_ms": None,
            "team": team,
            "track_id": None,
            "track_id_to": None,
            "zone": None,
        })
    return shot_events


def _detect_pressing(
    ball_by_frame: Dict[int, Tuple[float, float]],
    players_by_frame: Dict[int, List[Tuple[int, int, float, float]]],
    params: Dict,
    fps: float,
) -> List[Dict]:
    """Pressing: conteggio giocatori nel raggio attorno alla palla; evento quando supera soglia."""
    pressing_events = []
    radius_m = params.get("radius_around_ball_m", 5.0)
    min_players = params.get("min_players_to_count_pressing", 1)
    frames_sorted = sorted(set(ball_by_frame.keys()) & set(players_by_frame.keys()))
    for frame_idx in frames_sorted:
        ball_pt = ball_by_frame.get(frame_idx)
        players = players_by_frame.get(frame_idx, [])
        if not ball_pt or not players:
            continue
        bx, by = ball_pt
        count_team: Dict[int, int] = {}
        for tid, team, px, py in players:
            if _dist_m(bx, by, px, py) <= radius_m:
                count_team[team] = count_team.get(team, 0) + 1
        for team, count in count_team.items():
            if count >= min_players:
                ts_ms = int(frame_idx * 1000 / fps) if fps else 0
                pressing_events.append({
                    "type": "pressing",
                    "timestamp_ms": ts_ms,
                    "end_ms": None,
                    "team": team,
                    "track_id": None,
                    "track_id_to": None,
                    "zone": f"count_{count}",
                })
    return pressing_events


def run_event_engine(
    player_tracks: Dict[str, Any],
    ball_tracks: Dict[str, Any],
    fps: float,
    calibration_path: Optional[str] = None,
    params: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Esegue l'event engine su player_tracks e ball_tracks.
    Ritorna un dict con:
      - possession_segments: [{start_frame, end_frame, team, track_id}, ...]
      - automatic: lista eventi in formato schema Step 0.1 (type, timestamp_ms, team, track_id, ...)
    """
    if params is None:
        params = get_params()
    pos_params = params.get("possession", {})
    max_dist_m = pos_params.get("max_ball_player_distance_m", 2.0)
    min_time_s = pos_params.get("min_possession_time_s", 0.5)
    pass_params = params.get("events", {}).get("pass", {})
    recovery_params = params.get("events", {}).get("recovery", {})
    shot_params = params.get("events", {}).get("shot", {})
    pressing_params = params.get("events", {}).get("pressing", {})
    field = params.get("field", {})
    field_length_m = field.get("length_m", 105)
    field_width_m = field.get("width_m", 68)

    width = player_tracks.get("width") or ball_tracks.get("width") or 1280
    height = player_tracks.get("height") or ball_tracks.get("height") or 720
    calibrator = get_calibrator(calibration_path) if calibration_path else None

    ball_by_frame, players_by_frame, _ = _build_frame_data(
        player_tracks, ball_tracks, calibrator, width, height, field_length_m, field_width_m
    )
    min_frames = max(1, int(min_time_s * fps))
    possession_segments, possession_by_frame = _compute_possession(
        ball_by_frame, players_by_frame, max_dist_m, min_frames, fps
    )

    automatic: List[Dict] = []
    automatic.extend(_detect_passes(possession_by_frame, ball_by_frame, pass_params, fps))
    automatic.extend(_detect_recoveries(possession_by_frame, ball_by_frame, recovery_params, fps))
    automatic.extend(_detect_shots(ball_by_frame, shot_params, fps))
    automatic.extend(_detect_pressing(ball_by_frame, players_by_frame, pressing_params, fps))
    automatic.sort(key=lambda e: e["timestamp_ms"])

    return {
        "possession_segments": possession_segments,
        "automatic": automatic,
    }


def run_event_engine_from_project(
    project_analysis_dir: str,
    fps: float,
    progress_callback: Optional[Any] = None,
) -> bool:
    """
    Carica player_tracks e ball_tracks dalla cartella progetto, eventuale calibrazione,
    esegue run_event_engine e scrive events_engine.json in analysis_output/detections/.
    Ritorna True se ok.
    """
    from .config import get_calibration_path, get_analysis_output_path
    from .player_tracking import get_tracks_path
    from .ball_tracking import get_ball_tracks_path

    output_base = Path(project_analysis_dir)
    detections_dir = get_analysis_output_path(project_analysis_dir) / "detections"
    pt_path = get_tracks_path(project_analysis_dir)
    bt_path = get_ball_tracks_path(project_analysis_dir)
    cal_path = get_calibration_path(project_analysis_dir)

    if not pt_path.exists() or not bt_path.exists():
        return False
    with open(pt_path, "r", encoding="utf-8") as f:
        player_tracks = json.load(f)
    with open(bt_path, "r", encoding="utf-8") as f:
        ball_tracks = json.load(f)

    fps_pt = player_tracks.get("fps") or fps
    fps_bt = ball_tracks.get("fps") or fps
    fps_use = fps_pt if fps_pt else fps

    if progress_callback:
        progress_callback(0, 1, "Event engine...")
    result = run_event_engine(
        player_tracks,
        ball_tracks,
        fps_use,
        calibration_path=str(cal_path) if cal_path.exists() else None,
    )
    if progress_callback:
        progress_callback(1, 1, "Event engine completato.")

    out_path = detections_dir / "events_engine.json"
    detections_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    return True
