"""
Metriche automatiche (Fase 7): per giocatore e per squadra.
Eseguito dopo event engine; usa stesse soglie/parametri (Fase 5) e calibrazione.
Output nel formato unico (metrics.players, metrics.teams).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .event_engine_params import get_params
from .homography import get_calibrator


def _player_center(d: Dict) -> Tuple[float, float]:
    x, y = d["x"], d["y"]
    w, h = d.get("w", 0), d.get("h", 0)
    return (x + w / 2, y + h / 2)


def _dist_m(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


# Griglia heatmap: campo 105x68 m, cella 2m (circa 52x34)
HEATMAP_CELL_M = 2.0
FIELD_LENGTH_M = 105.0
FIELD_WIDTH_M = 68.0


def _cell_index(x_m: float, y_m: float) -> Tuple[int, int]:
    """Indice cella griglia (i, j) da coordinate metri. i lungo x, j lungo y."""
    i = max(0, min(int(x_m / HEATMAP_CELL_M), int(FIELD_LENGTH_M / HEATMAP_CELL_M) - 1))
    j = max(0, min(int(y_m / HEATMAP_CELL_M), int(FIELD_WIDTH_M / HEATMAP_CELL_M) - 1))
    return (i, j)


def _build_trajectories_m(
    player_tracks: Dict,
    calibrator: Optional[Any],
    width: int,
    height: int,
    scale: float,
) -> Dict[int, List[Tuple[int, float, float]]]:
    """
    Ritorna track_id -> lista (frame_idx, x_m, y_m) per ogni frame in cui il giocatore è presente.
    """
    field_l = get_params().get("field", {}).get("length_m", FIELD_LENGTH_M)
    field_w = get_params().get("field", {}).get("width_m", FIELD_WIDTH_M)
    scale_use = scale if scale > 0 else field_l / width if width else 0.05
    trajectories: Dict[int, List[Tuple[int, float, float]]] = {}
    for f in player_tracks.get("frames", []):
        frame_idx = f.get("frame", 0)
        for d in f.get("detections", []):
            tid = d.get("track_id", -1)
            cx, cy = _player_center(d)
            if calibrator:
                pt_m = calibrator.pixel_to_field(cx, cy)
                if pt_m:
                    x_m, y_m = pt_m[0], pt_m[1]
                else:
                    x_m, y_m = cx * scale_use, cy * scale_use
            else:
                x_m, y_m = cx * scale_use, cy * scale_use
            if tid not in trajectories:
                trajectories[tid] = []
            trajectories[tid].append((frame_idx, x_m, y_m))
    return trajectories


def _distance_from_trajectory(positions: List[Tuple[int, float, float]]) -> float:
    """Distanza totale in metri: somma segmenti tra frame consecutivi."""
    if len(positions) < 2:
        return 0.0
    total = 0.0
    pos_sorted = sorted(positions, key=lambda p: p[0])
    for k in range(1, len(pos_sorted)):
        _, x0, y0 = pos_sorted[k - 1]
        _, x1, y1 = pos_sorted[k]
        total += _dist_m(x0, y0, x1, y1)
    return round(total, 2)


def _heatmap_grid(positions: List[Tuple[int, float, float]]) -> List[List[int]]:
    """Griglia 2D: conteggio frame per cella. Dimensioni da FIELD e HEATMAP_CELL_M."""
    ni = int(FIELD_LENGTH_M / HEATMAP_CELL_M)
    nj = int(FIELD_WIDTH_M / HEATMAP_CELL_M)
    grid = [[0] * nj for _ in range(ni)]
    for _, x_m, y_m in positions:
        i, j = _cell_index(x_m, y_m)
        if 0 <= i < ni and 0 <= j < nj:
            grid[i][j] += 1
    return grid


# Zone: terzi (x), corridoi (y) - campo 105x68
def _zone_labels(x_m: float, y_m: float) -> Dict[str, str]:
    """Etichette zona: third (def/mid/att), corridor (left/center/right)."""
    third = "def" if x_m < 35 else ("mid" if x_m < 70 else "att")
    corridor = "left" if y_m < 22.67 else ("center" if y_m < 45.33 else "right")
    return {"third": third, "corridor": corridor}


def _zones_pct(positions: List[Tuple[int, float, float]]) -> Dict[str, float]:
    """Percentuale tempo per zona (terzi e corridoi)."""
    if not positions:
        return {}
    counts: Dict[str, int] = {}
    for _, x_m, y_m in positions:
        labels = _zone_labels(x_m, y_m)
        for k, v in labels.items():
            key = f"{k}_{v}"
            counts[key] = counts.get(key, 0) + 1
    total = len(positions)
    return {k: round(100.0 * v / total, 1) for k, v in counts.items()}


def compute_metrics(
    player_tracks: Dict[str, Any],
    ball_tracks: Dict[str, Any],
    events_result: Dict[str, Any],
    calibration_path: Optional[str] = None,
    fps: float = 10.0,
) -> Dict[str, Any]:
    """
    Calcola metriche per giocatore e per squadra.
    events_result: output di event_engine (possession_segments, automatic).
    Ritorna { "players": [...], "teams": [...] } nel formato schema Step 0.1.
    """
    params = get_params()
    field = params.get("field", {})
    field_l = field.get("length_m", FIELD_LENGTH_M)
    field_w = field.get("width_m", FIELD_WIDTH_M)
    width = player_tracks.get("width") or ball_tracks.get("width") or 1280
    height = player_tracks.get("height") or ball_tracks.get("height") or 720
    scale = field_l / width if width else 0.05
    calibrator = get_calibrator(calibration_path) if calibration_path else None

    possession_segments = events_result.get("possession_segments", [])
    automatic = events_result.get("automatic", [])

    trajectories = _build_trajectories_m(player_tracks, calibrator, width, height, scale)

    # Set di track_id con team (da segmenti o da trajectory con team dal primo frame)
    track_team: Dict[int, int] = {}
    for seg in possession_segments:
        track_team[seg["track_id"]] = seg["team"]
    pt_frames = {f["frame"]: f for f in player_tracks.get("frames", [])}
    for frame_idx, f in sorted(pt_frames.items()):
        for d in f.get("detections", []):
            tid = d.get("track_id", -1)
            if tid not in track_team:
                track_team[tid] = d.get("team", -1)

    # --- Per giocatore ---
    pass_events = [e for e in automatic if e.get("type") == "pass"]
    touches_by_track: Dict[int, int] = {}  # frame count in possession
    for seg in possession_segments:
        tid = seg["track_id"]
        n_frames = seg["end_frame"] - seg["start_frame"] + 1
        touches_by_track[tid] = touches_by_track.get(tid, 0) + n_frames

    players_list: List[Dict] = []
    for track_id, positions in trajectories.items():
        team = track_team.get(track_id, -1)
        distance_m = _distance_from_trajectory(positions)
        heatmap_grid = _heatmap_grid(positions)
        zones_pct = _zones_pct(positions)
        passes = sum(1 for e in pass_events if e.get("track_id") == track_id)
        passes_success = sum(1 for e in pass_events if e.get("track_id_to") == track_id or e.get("track_id") == track_id)
        touches = touches_by_track.get(track_id, 0)
        players_list.append({
            "track_id": track_id,
            "team": team,
            "distance_m": distance_m,
            "heatmap_grid": heatmap_grid,
            "zones_pct": zones_pct,
            "passes": passes,
            "passes_success": passes_success,
            "touches": touches,
        })
    players_list.sort(key=lambda p: (p["team"], p["track_id"]))

    # --- Per squadra ---
    # Totale frame con possesso assegnato (unione segmenti)
    all_frames = set()
    for seg in possession_segments:
        for fr in range(seg["start_frame"], seg["end_frame"] + 1):
            all_frames.add(fr)
    total_frames = len(all_frames) if all_frames else 1

    team_frames: Dict[int, int] = {}
    for seg in possession_segments:
        t = seg["team"]
        n = seg["end_frame"] - seg["start_frame"] + 1
        team_frames[t] = team_frames.get(t, 0) + n
    possession_pct_by_team: Dict[int, float] = {}
    for t, n in team_frames.items():
        possession_pct_by_team[t] = round(100.0 * n / total_frames, 1) if total_frames else 0.0

    passes_by_team: Dict[int, int] = {}
    for e in pass_events:
        t = e.get("team")
        if t is not None:
            passes_by_team[t] = passes_by_team.get(t, 0) + 1

    # Pressure map: media delle heatmap dei giocatori della squadra (griglia somma poi normalizzata o lasciata come conteggio)
    pressure_by_team: Dict[int, List[List[int]]] = {}
    for p in players_list:
        t = p["team"]
        if t not in pressure_by_team:
            ni = int(FIELD_LENGTH_M / HEATMAP_CELL_M)
            nj = int(FIELD_WIDTH_M / HEATMAP_CELL_M)
            pressure_by_team[t] = [[0] * nj for _ in range(ni)]
        grid = p.get("heatmap_grid") or []
        for i, row in enumerate(grid):
            for j, v in enumerate(row):
                if i < len(pressure_by_team[t]) and j < len(pressure_by_team[t][i]):
                    pressure_by_team[t][i][j] += v

    # Recovery zone media: da eventi recovery (zone "left"/"right" -> approssimazione centro zona)
    recovery_events = [e for e in automatic if e.get("type") == "recovery"]
    recovery_zone_by_team: Dict[int, List[List[float]]] = {}
    for e in recovery_events:
        t = e.get("team")
        if t is None:
            continue
        zone = e.get("zone", "mid")
        if zone == "left":
            recovery_zone_by_team.setdefault(t, []).append([8.5, 34.0])
        elif zone == "right":
            recovery_zone_by_team.setdefault(t, []).append([96.5, 34.0])
        else:
            recovery_zone_by_team.setdefault(t, []).append([52.5, 34.0])
    recovery_zone_avg: Dict[int, Optional[List[float]]] = {}
    for t, points in recovery_zone_by_team.items():
        if points:
            avg_x = sum(p[0] for p in points) / len(points)
            avg_y = sum(p[1] for p in points) / len(points)
            recovery_zone_avg[t] = [round(avg_x, 1), round(avg_y, 1)]
        else:
            recovery_zone_avg[t] = None
    team_ids = sorted(set(track_team.values()) | set(team_frames.keys()) | set(passes_by_team.keys()))
    team_ids = [t for t in team_ids if t >= 0]
    teams_list: List[Dict] = []
    for t in team_ids:
        teams_list.append({
            "team_id": t,
            "possession_pct": possession_pct_by_team.get(t, 0.0),
            "passes_total": passes_by_team.get(t, 0),
            "pressure_map": pressure_by_team.get(t),
            "recovery_zone_avg": recovery_zone_avg.get(t),
        })
    teams_list.sort(key=lambda x: x["team_id"])

    return {
        "players": players_list,
        "teams": teams_list,
    }


def run_metrics_from_project(
    project_analysis_dir: str,
    fps: float,
    progress_callback: Optional[Any] = None,
) -> bool:
    """
    Carica player_tracks, ball_tracks, events_engine.json dalla cartella progetto,
    esegue compute_metrics e scrive metrics.json in analysis_output/.
    Ritorna True se ok. Richiede che event_engine sia già stato eseguito.
    """
    from .config import get_calibration_path, get_analysis_output_path
    from .player_tracking import get_tracks_path
    from .ball_tracking import get_ball_tracks_path

    output_base = Path(project_analysis_dir)
    analysis_output = get_analysis_output_path(project_analysis_dir)
    detections_dir = analysis_output / "detections"
    pt_path = get_tracks_path(project_analysis_dir)
    bt_path = get_ball_tracks_path(project_analysis_dir)
    cal_path = get_calibration_path(project_analysis_dir)
    events_path = detections_dir / "events_engine.json"

    if not pt_path.exists() or not bt_path.exists():
        return False
    if not events_path.exists():
        return False
    with open(pt_path, "r", encoding="utf-8") as f:
        player_tracks = json.load(f)
    with open(bt_path, "r", encoding="utf-8") as f:
        ball_tracks = json.load(f)
    with open(events_path, "r", encoding="utf-8") as f:
        events_result = json.load(f)

    fps_pt = player_tracks.get("fps") or fps
    fps_use = fps_pt if fps_pt else fps

    if progress_callback:
        progress_callback(0, 1, "Metriche...")
    result = compute_metrics(
        player_tracks,
        ball_tracks,
        events_result,
        calibration_path=str(cal_path) if cal_path.exists() else None,
        fps=fps_use,
    )
    if progress_callback:
        progress_callback(1, 1, "Metriche completate.")

    out_path = analysis_output / "metrics.json"
    analysis_output.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    return True
