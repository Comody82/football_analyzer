"""
Modulo condiviso per soglie e parametri dell'event engine e delle metriche (Fase 5).
Usato da analisi locale e da backend cloud; legge da config/event_engine_params.json
con fallback su valori di default se il file non esiste o è incompleto.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

# Nome file config (cercato in config/ rispetto alla root del progetto)
CONFIG_FILENAME = "event_engine_params.json"

# Default se file assente o campi mancanti (allineati a config/event_engine_params.json)
DEFAULT_PARAMS = {
    "version": "1.0",
    "possession": {
        "max_ball_player_distance_m": 2.0,
        "min_possession_time_s": 0.5,
        "change_possession_on_opponent_control": True,
        "change_possession_distance_m": 2.0,
    },
    "events": {
        "pass": {
            "use_possession": True,
            "max_ball_receiver_distance_m": 3.0,
            "same_team_required": True,
        },
        "recovery": {
            "defensive_area_x_min_m": 0,
            "defensive_area_x_max_m": 17,
            "defensive_area_x_max_other_side_m": 88,
            "defensive_area_x_min_other_side_m": 105,
        },
        "shot": {
            "min_ball_speed_m_s": 8.0,
            "goal_center_y_m": 34,
            "goal_left_x_m": 0,
            "goal_right_x_m": 105,
            "max_angle_deg_from_goal": 45,
            "min_shot_interval_ms": 1500,
        },
        "pressing": {
            "radius_around_ball_m": 5.0,
            "min_players_to_count_pressing": 1,
        },
    },
    "field": {
        "length_m": 105,
        "width_m": 68,
    },
}

_cached: Optional[Dict[str, Any]] = None
_cached_path: Optional[str] = None


def _project_root() -> Path:
    """Root del progetto (cartella che contiene 'analysis' e 'config')."""
    # Questo modulo è in analysis/event_engine_params.py
    here = Path(__file__).resolve().parent
    root = here.parent
    return root


def _config_path() -> Path:
    """Percorso del file JSON dei parametri (config/ nella root)."""
    return _project_root() / "config" / CONFIG_FILENAME


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge ricorsivo: override ha precedenza, base riempie i buchi."""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_params(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Carica i parametri da config/event_engine_params.json (o dal path indicato).
    Restituisce un dict con le stesse chiavi di DEFAULT_PARAMS; valori mancanti
    nel file sono sostituiti dai default. Se il file non esiste, restituisce
    una copia di DEFAULT_PARAMS.
    """
    global _cached, _cached_path
    path = config_path or _config_path()
    path_str = str(path.resolve())
    if _cached is not None and _cached_path == path_str:
        return _cached
    result = dict(DEFAULT_PARAMS)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                result = _deep_merge(result, data)
        except (json.JSONDecodeError, OSError):
            pass
    _cached = result
    _cached_path = path_str
    return result


def get_params(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Alias di load_params(): restituisce i parametri (cached dopo la prima lettura).
    Uso tipico in event engine e metriche:

      from analysis.event_engine_params import get_params
      p = get_params()
      max_dist = p["possession"]["max_ball_player_distance_m"]
      radius = p["events"]["pressing"]["radius_around_ball_m"]
    """
    return load_params(config_path)


def get_possession_params(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Solo la sezione possession."""
    return get_params(config_path).get("possession", DEFAULT_PARAMS["possession"])


def get_event_params(event_name: str, config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Parametri per un tipo di evento (pass, recovery, shot, pressing)."""
    events = get_params(config_path).get("events", DEFAULT_PARAMS["events"])
    return events.get(event_name, {})


def get_field_params(config_path: Optional[Path] = None) -> Dict[str, float]:
    """Dimensioni campo (metri)."""
    return get_params(config_path).get("field", DEFAULT_PARAMS["field"])


def clear_cache():
    """Invalida la cache (utile dopo aver riscritto il file da UI o test)."""
    global _cached, _cached_path
    _cached = None
    _cached_path = None
