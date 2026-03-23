"""
Repository squadre e giocatori (database locale JSON).
Gestisce il catalogo squadre con rosa, ruoli e metadati.
"""
from __future__ import annotations

import csv
import io
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# ── Costanti ────────────────────────────────────────────────────────────────
ROLES = [
    "POR",   # Portiere
    "DIF",   # Difensore
    "CEN",   # Centrocampista
    "ATT",   # Attaccante
    "ALT",   # Altro / Non specificato
]

_DEFAULT_DB_PATH = Path("data/teams.json")


# ── Modelli ─────────────────────────────────────────────────────────────────
@dataclass
class Player:
    id: str
    name: str
    jersey_number: Optional[int]
    role: str

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name,
                "jersey_number": self.jersey_number, "role": self.role}

    @classmethod
    def from_dict(cls, d: dict) -> "Player":
        return cls(
            id=str(d.get("id", uuid.uuid4())),
            name=str(d.get("name", "")),
            jersey_number=int(d["jersey_number"]) if d.get("jersey_number") is not None else None,
            role=str(d.get("role", "ALT")),
        )


@dataclass
class Team:
    id: str
    name: str
    color: str
    country: str
    league: str
    logo_path: Optional[str]
    players: List[Player] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "color": self.color,
            "country": self.country, "league": self.league,
            "logo_path": self.logo_path,
            "players": [p.to_dict() for p in self.players],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Team":
        return cls(
            id=str(d.get("id", uuid.uuid4())),
            name=str(d.get("name", "")),
            color=str(d.get("color", "#3b82f6")),
            country=str(d.get("country", "")),
            league=str(d.get("league", "")),
            logo_path=d.get("logo_path"),
            players=[Player.from_dict(p) for p in d.get("players", [])],
        )


# ── Repository ───────────────────────────────────────────────────────────────
class TeamsRepository:
    """
    Database locale squadre/giocatori salvato in JSON.

    Uso:
        repo = TeamsRepository()                        # path default
        repo = TeamsRepository("mio_percorso/db.json") # path custom
    """

    def __init__(self, db_path: str = None):
        self._path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._teams: List[Team] = []
        self._load()

    # ── I/O ──────────────────────────────────────────────────────────────────
    def _load(self):
        if not self._path.exists():
            self._teams = []
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._teams = [Team.from_dict(t) for t in data.get("teams", [])]
        except Exception:
            self._teams = []

    def _save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump({"teams": [t.to_dict() for t in self._teams]}, f,
                      indent=2, ensure_ascii=False)

    # ── Query ─────────────────────────────────────────────────────────────────
    def list_teams(self) -> List[Team]:
        return list(self._teams)

    def get_team(self, team_id: str) -> Optional[Team]:
        return next((t for t in self._teams if t.id == team_id), None)

    def list_countries(self) -> List[str]:
        return sorted({t.country for t in self._teams if t.country})

    def list_leagues(self, country: str = "") -> List[str]:
        return sorted({
            t.league for t in self._teams
            if t.league and (not country or t.country == country)
        })

    # ── Squadre ───────────────────────────────────────────────────────────────
    def add_team(self, name: str, color: str = "#3b82f6",
                 logo_path: str = None, country: str = "", league: str = "") -> Team:
        team = Team(id=str(uuid.uuid4()), name=name.strip(), color=color or "#3b82f6",
                    country=country, league=league, logo_path=logo_path)
        self._teams.append(team)
        self._save()
        return team

    def update_team(self, team_id: str, name: str = None, color: str = None,
                    logo_path: str = None, country: str = None, league: str = None):
        team = self.get_team(team_id)
        if not team:
            return
        if name is not None:
            team.name = name.strip() or team.name
        if color is not None:
            team.color = color
        if logo_path is not None:
            team.logo_path = logo_path
        if country is not None:
            team.country = country
        if league is not None:
            team.league = league
        self._save()

    def delete_team(self, team_id: str):
        self._teams = [t for t in self._teams if t.id != team_id]
        self._save()

    # ── Giocatori ─────────────────────────────────────────────────────────────
    def add_player(self, team_id: str, name: str,
                   jersey_number: Optional[int] = None,
                   role: str = "ALT") -> Optional[Player]:
        team = self.get_team(team_id)
        if not team:
            return None
        player = Player(id=str(uuid.uuid4()), name=name.strip(),
                        jersey_number=jersey_number,
                        role=role if role in ROLES else "ALT")
        team.players.append(player)
        self._save()
        return player

    def update_player(self, team_id: str, player_id: str,
                      name: str = None, jersey_number: Optional[int] = None,
                      role: str = None):
        team = self.get_team(team_id)
        if not team:
            return
        player = next((p for p in team.players if p.id == player_id), None)
        if not player:
            return
        if name is not None:
            player.name = name.strip() or player.name
        if jersey_number is not None:
            player.jersey_number = jersey_number
        if role is not None:
            player.role = role if role in ROLES else player.role
        self._save()

    def delete_player(self, team_id: str, player_id: str):
        team = self.get_team(team_id)
        if not team:
            return
        team.players = [p for p in team.players if p.id != player_id]
        self._save()

    def import_from_csv(self, team_id: str, csv_text: str) -> int:
        """
        Importa giocatori da testo CSV.
        Formato atteso: name,jersey_number,role  (header opzionale)
        Ritorna il numero di giocatori importati.
        """
        team = self.get_team(team_id)
        if not team:
            return 0
        count = 0
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            name = (row.get("name") or row.get("Nome") or "").strip()
            if not name:
                continue
            try:
                num_raw = row.get("jersey_number") or row.get("numero") or ""
                jersey = int(num_raw.strip()) if num_raw.strip() else None
            except ValueError:
                jersey = None
            role_raw = (row.get("role") or row.get("ruolo") or "ALT").strip().upper()
            role = role_raw if role_raw in ROLES else "ALT"
            team.players.append(Player(id=str(uuid.uuid4()), name=name,
                                       jersey_number=jersey, role=role))
            count += 1
        if count:
            self._save()
        return count
