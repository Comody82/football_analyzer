"""Calcolo statistiche dalla partita."""
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from .events import Event, EventManager


@dataclass
class MatchStatistics:
    """Statistiche di partita."""
    # Conteggi per squadra
    home_goals: int = 0
    away_goals: int = 0
    home_shots_on: int = 0
    away_shots_on: int = 0
    home_shots_off: int = 0
    away_shots_off: int = 0
    home_corners: int = 0
    away_corners: int = 0
    home_passes: int = 0  # placeholder - va implementato con tag passaggio
    away_passes: int = 0

    # Possesso (percentuale home, calcolato se disponibile)
    possession_home_pct: Optional[float] = None
    possession_away_pct: Optional[float] = None

    # Distanze (placeholder - richiedono tracking manuale o CV)
    distance_home_team: Optional[float] = None  # metri
    distance_away_team: Optional[float] = None
    distance_per_player: Dict[str, float] = field(default_factory=dict)  # player_id -> metri


class StatisticsManager:
    """Calcola statistiche dagli eventi."""

    def __init__(self, event_manager: EventManager):
        self._em = event_manager

    def compute(self, duration_ms: int = 0) -> MatchStatistics:
        """Calcola statistiche. Non usa gli eventi (tasti evento e statistiche sono scollegati)."""
        return MatchStatistics()

    def get_summary_dict(self, stats: MatchStatistics) -> Dict[str, any]:
        """Ritorna un dict per visualizzazione."""
        return {
            "Gol Casa": stats.home_goals,
            "Gol Ospiti": stats.away_goals,
            "Tiri in Porta Casa": stats.home_shots_on,
            "Tiri in Porta Ospiti": stats.away_shots_on,
            "Tiri Fuori Casa": stats.home_shots_off,
            "Tiri Fuori Ospiti": stats.away_shots_off,
            "Calci d'Angolo Casa": stats.home_corners,
            "Calci d'Angolo Ospiti": stats.away_corners,
            "Passaggi Casa": stats.home_passes,
            "Passaggi Ospiti": stats.away_passes,
            "Possesso Casa %": stats.possession_home_pct,
            "Possesso Ospiti %": stats.possession_away_pct,
            "Distanza Casa (m)": stats.distance_home_team,
            "Distanza Ospiti (m)": stats.distance_away_team,
        }
