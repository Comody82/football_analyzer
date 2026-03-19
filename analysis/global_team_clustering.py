"""
Clustering globale squadre: un solo KMeans k=3 su tutti i campioni jersey (HSV)
del video, poi assegnazione team coerente per tutto il video.

Legge player_tracks.json (con jersey_hsv per detection), ricalcola team e sovrascrive il file.
"""
import json
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np
from sklearn.cluster import KMeans

from .player_tracking import get_tracks_path
from .team_classifier import (
    _REF_REFEREE_HSV,
    _REF_REFEREE_YELLOW_HSV,
    _REF_WHITE_HSV,
    _distance_to_red,
    _hsv_distance,
    _is_referee_jersey_hsv,
)


def run_global_team_clustering(
    project_analysis_dir: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> bool:
    """
    Raccoglie tutti i jersey_hsv da player_tracks.json, esegue KMeans k=3,
    assegna team (0, 1, -1) per centroide e sovrascrive il campo team in player_tracks.

    Ritorna True se completato (anche se nessun campione: file non modificato).
    """
    tracks_path = get_tracks_path(project_analysis_dir)
    path = Path(tracks_path)
    if not path.exists():
        return False

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    frames_data = data.get("frames", [])
    if not frames_data:
        return True

    # Raccogli campioni HSV (uno per detection che ha jersey_hsv)
    samples: List[List[float]] = []
    # Mappa indice (frame_idx, det_idx) -> indice in samples (per riassegnare dopo)
    # In realtà dobbiamo riassegnare ogni detection: per ogni frame, per ogni det con jersey_hsv,
    # troviamo il centroide più vicino e assegniamo team.
    samples_per_detection: List[tuple] = []  # (frame_idx, det_idx_in_frame, [h,s,v])

    for frame_idx, fd in enumerate(frames_data):
        for det_idx, d in enumerate(fd.get("detections", [])):
            hsv = d.get("jersey_hsv")
            if not hsv or len(hsv) < 3:
                continue
            h, s, v = float(hsv[0]), float(hsv[1]), float(hsv[2])
            samples.append([h, s, v])
            samples_per_detection.append((frame_idx, det_idx))

    if progress_callback:
        progress_callback(0, 1, "Clustering globale squadre...")

    if len(samples) < 3:
        # Troppi pochi campioni: lascia team invariato
        if progress_callback:
            progress_callback(1, 1, "Completato (pochi campioni, team invariati)")
        return True

    X = np.array(samples)
    kmeans = KMeans(n_clusters=3, random_state=42, n_init=15)
    labels = kmeans.fit_predict(X)
    centers = [tuple(c) for c in kmeans.cluster_centers_]

    # Quale cluster è arbitro? Distanza minima da giallo/lime; fallback: cluster più piccolo (arbitro = 1 persona)
    d_ref_lime = [_hsv_distance(c, _REF_REFEREE_HSV) for c in centers]
    d_ref_yellow = [_hsv_distance(c, _REF_REFEREE_YELLOW_HSV) for c in centers]
    d_ref = [min(d_ref_lime[i], d_ref_yellow[i]) for i in range(3)]
    referee_cluster = int(np.argmin(d_ref))
    h, s, v = centers[referee_cluster][0], centers[referee_cluster][1], centers[referee_cluster][2]
    if not _is_referee_jersey_hsv(h, s, v):
        # Fallback: il cluster con meno detection è probabilmente l'arbitro (una sola persona)
        counts = [int(np.sum(labels == i)) for i in range(3)]
        min_count_idx = int(np.argmin(counts))
        # Arbitro = 1 persona: cluster con meno detection (solo se chiaramente più piccolo)
        mean_count = (sum(counts) - counts[min_count_idx]) / 2
        if mean_count > 0 and counts[min_count_idx] < 0.75 * mean_count:
            referee_cluster = min_count_idx
        else:
            referee_cluster = -1

    # Mappa cluster -> team (0, 1, -1)
    label_to_team = {}
    if referee_cluster >= 0:
        team_clusters = [i for i in range(3) if i != referee_cluster]
        c_a, c_b = centers[team_clusters[0]], centers[team_clusters[1]]
        d_a_white = _hsv_distance(c_a, _REF_WHITE_HSV)
        d_b_white = _hsv_distance(c_b, _REF_WHITE_HSV)
        d_a_red = _distance_to_red(c_a)
        d_b_red = _distance_to_red(c_b)
        if d_a_white + d_b_red < d_a_red + d_b_white:
            label_to_team = {team_clusters[0]: 0, team_clusters[1]: 1, referee_cluster: -1}
        else:
            label_to_team = {team_clusters[0]: 1, team_clusters[1]: 0, referee_cluster: -1}
    else:
        for i in range(3):
            d_white = _hsv_distance(centers[i], _REF_WHITE_HSV)
            d_red = _distance_to_red(centers[i])
            label_to_team[i] = 0 if d_white < d_red else 1

    # Riassegna team per ogni detection che ha jersey_hsv (usa il label del suo campione)
    for idx, (frame_idx, det_idx) in enumerate(samples_per_detection):
        lab = int(labels[idx])
        new_team = label_to_team.get(lab, 0)
        frame_data = frames_data[frame_idx]
        detections = frame_data.get("detections", [])
        if det_idx < len(detections):
            detections[det_idx]["team"] = new_team

    # Stabilizza team per track_id: un track = un team (moda sui frame)
    from collections import Counter
    track_teams: dict = {}
    for fd in frames_data:
        for d in fd.get("detections", []):
            tid = d.get("track_id")
            if tid is None:
                continue
            t = d.get("team", 0)
            if tid not in track_teams:
                track_teams[tid] = []
            track_teams[tid].append(t)
    track_mode = {}
    for tid, teams in track_teams.items():
        cnt = Counter(teams)
        track_mode[tid] = cnt.most_common(1)[0][0]
    for fd in frames_data:
        for d in fd.get("detections", []):
            tid = d.get("track_id")
            if tid is not None and tid in track_mode:
                d["team"] = track_mode[tid]

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    if progress_callback:
        progress_callback(1, 1, "Clustering globale completato")
    return True
