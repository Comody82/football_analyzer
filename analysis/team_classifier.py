"""
Team classification per analisi automatica.
Classifica giocatori in 2 squadre tramite KMeans sui colori maglia (HSV).
Usa la metà superiore del bbox come regione maglia.
"""
from typing import List, Tuple
import cv2
import numpy as np
from sklearn.cluster import KMeans

from .player_detection import BoundingBox


def extract_jersey_region(
    frame: np.ndarray,
    bbox: BoundingBox,
    margin_ratio: float = 0.1,
) -> np.ndarray:
    """
    Estrae la regione maglia (metà superiore del bbox).
    Ritorna immagine ritagliata in BGR.
    """
    h_img, w_img = frame.shape[:2]
    x = max(0, int(bbox.x))
    y = max(0, int(bbox.y))
    w = max(1, int(bbox.w))
    h = max(1, int(bbox.h))
    # Prendi metà superiore (maglia)
    h_top = max(1, h // 2)
    # Margine
    mw = max(1, int(w * margin_ratio))
    mh = max(1, int(h_top * margin_ratio))
    x1 = max(0, x - mw)
    y1 = max(0, y - mh)
    x2 = min(w_img, x + w + mw)
    y2 = min(h_img, y + h_top + mh)
    return frame[y1:y2, x1:x2]


def extract_dominant_colors_hsv(
    region: np.ndarray,
    n_colors: int = 3,
) -> List[Tuple[float, float, float]]:
    """
    Estrae colori dominanti in HSV dalla regione.
    Ritorna lista di (H, S, V).
    """
    if region.size == 0:
        return [(0, 0, 0)]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    pixels = hsv.reshape(-1, 3).astype(np.float32)
    # Campiona se troppi pixel
    if len(pixels) > 2000:
        idx = np.random.choice(len(pixels), 2000, replace=False)
        pixels = pixels[idx]
    try:
        kmeans = KMeans(n_clusters=min(n_colors, len(pixels)), random_state=42, n_init=10)
        kmeans.fit(pixels)
        return [tuple(float(x) for x in c) for c in kmeans.cluster_centers_]
    except Exception:
        return [(0, 0, 0)]


def _is_referee_jersey_hsv(h: float, s: float, v: float) -> bool:
    """Indica se il colore è tipico maglia arbitro (giallo, giallo-verde lime, giallo/nero).
    Range H ampliato per gialli classici e lime; S/V sufficienti per escludere bianco/scuro."""
    h, s, v = float(h), float(s), float(v)
    if s < 80 or v < 100:
        return False
    # Giallo classico H~25-35, lime/verde-giallo H~40-70, giallo-arancio H~18-25 (no rosso)
    if h <= 15 or h >= 85:  # escludi rosso (0, 180) e verde puro
        return False
    return 18 <= h <= 75  # giallo → lime


# Riferimenti HSV per ordinare i cluster in modo coerente (squadra chiara vs rossa/scura)
_REF_WHITE_HSV = (30.0, 80.0, 220.0)    # bianco
_REF_RED_HSV = (0.0, 180.0, 150.0)      # rosso brillante
_REF_RED_DARK_HSV = (0.0, 200.0, 90.0)  # rosso scuro / bordò
_REF_REFEREE_HSV = (50.0, 200.0, 220.0) # giallo-verde lime
_REF_REFEREE_YELLOW_HSV = (30.0, 200.0, 220.0)  # giallo classico


def _hsv_distance(c: Tuple[float, float, float], ref: Tuple[float, float, float]) -> float:
    """Distanza approssimata in spazio HSV (H 0-180, S/V 0-255)."""
    dh = min(abs(c[0] - ref[0]), 180 - abs(c[0] - ref[0]))
    ds = (c[1] - ref[1]) / 255.0
    dv = (c[2] - ref[2]) / 255.0
    return dh * dh + ds * ds * 4 + dv * dv * 4


def _distance_to_red(c: Tuple[float, float, float]) -> float:
    """Distanza minima da rosso brillante o rosso scuro (maglia bordò)."""
    return min(_hsv_distance(c, _REF_RED_HSV), _hsv_distance(c, _REF_RED_DARK_HSV))


def classify_teams(
    frame: np.ndarray,
    boxes: List[BoundingBox],
) -> List[BoundingBox]:
    """
    Assegna team (0, 1 o -1) a ogni bbox.
    -1 = arbitro (cluster giallo-verde).
    0 = squadra chiara (bianco), 1 = squadra rossa/scura.
    Con 3+ giocatori usa K=3 (2 squadre + arbitro) per non mischiare l'arbitro con le squadre.
    Modifica boxes in-place e ritorna la lista.
    """
    if len(boxes) < 2:
        for b in boxes:
            b.team = 0
        return boxes

    features = []
    valid_idx = []
    for i, b in enumerate(boxes):
        reg = extract_jersey_region(frame, b)
        colors = extract_dominant_colors_hsv(reg, n_colors=2)
        best = max(colors, key=lambda c: c[1])
        features.append(best)
        valid_idx.append(i)

    X = np.array(features)
    n = len(features)

    if n >= 3:
        # K=3: due squadre + arbitro; etichettiamo i cluster in modo coerente
        kmeans = KMeans(n_clusters=3, random_state=42, n_init=15)
        labels_raw = kmeans.fit_predict(X)
        centers = [tuple(c) for c in kmeans.cluster_centers_]

        # Quale cluster è arbitro? Il cui centro è più vicino al riferimento giallo-verde
        d_ref = [_hsv_distance(c, _REF_REFEREE_HSV) for c in centers]
        referee_cluster = int(np.argmin(d_ref))
        h, s, v = centers[referee_cluster][0], centers[referee_cluster][1], centers[referee_cluster][2]
        if not _is_referee_jersey_hsv(h, s, v):
            referee_cluster = -1

        label_map = {}
        if referee_cluster >= 0:
            team_clusters = [i for i in range(3) if i != referee_cluster]
            c_a, c_b = centers[team_clusters[0]], centers[team_clusters[1]]
            d_a_white = _hsv_distance(c_a, _REF_WHITE_HSV)
            d_b_white = _hsv_distance(c_b, _REF_WHITE_HSV)
            d_a_red = _distance_to_red(c_a)
            d_b_red = _distance_to_red(c_b)
            if d_a_white + d_b_red < d_a_red + d_b_white:
                label_map = {team_clusters[0]: 0, team_clusters[1]: 1, referee_cluster: -1}
            else:
                label_map = {team_clusters[0]: 1, team_clusters[1]: 0, referee_cluster: -1}
        else:
            # Nessun arbitro: assegna i 3 cluster a 0 o 1 per vicinanza a bianco vs rosso
            for i in range(3):
                d_white = _hsv_distance(centers[i], _REF_WHITE_HSV)
                d_red = _distance_to_red(centers[i])
                label_map[i] = 0 if d_white < d_red else 1
        for j, i in enumerate(valid_idx):
            lab = int(labels_raw[j])
            boxes[i].team = label_map.get(lab, 0)
            boxes[i].jersey_hsv = tuple(float(x) for x in features[j])
    else:
        # 2 giocatori: K=2, eventuale arbitro già escluso dal colore
        referee_idx = []
        for j, i in enumerate(valid_idx):
            h, s, v = features[j][0], features[j][1], features[j][2]
            boxes[i].jersey_hsv = tuple(float(x) for x in features[j])
            if _is_referee_jersey_hsv(h, s, v):
                boxes[i].team = -1
                referee_idx.append(j)
        non_ref = [j for j in range(n) if j not in referee_idx]
        if len(non_ref) < 2:
            for j in non_ref:
                boxes[valid_idx[j]].team = 0
            return boxes
        sub_X = X[non_ref]
        kmeans = KMeans(n_clusters=2, random_state=42, n_init=10)
        labels_raw = kmeans.fit_predict(sub_X)
        centers = [tuple(c) for c in kmeans.cluster_centers_]
        d0_white = _hsv_distance(centers[0], _REF_WHITE_HSV)
        d1_white = _hsv_distance(centers[1], _REF_WHITE_HSV)
        d0_red = _distance_to_red(centers[0])
        d1_red = _distance_to_red(centers[1])
        cluster0_is_white = (d0_white + d1_red) < (d0_red + d1_white)
        label_map = {0: 0, 1: 1} if cluster0_is_white else {0: 1, 1: 0}
        for k, j in enumerate(non_ref):
            boxes[valid_idx[j]].team = label_map[int(labels_raw[k])]

    return boxes
