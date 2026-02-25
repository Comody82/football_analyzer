"""Gestione progetto e annotazioni sul video."""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import json
import os


@dataclass
class DrawingItem:
    """Elemento disegnato sul video."""
    id: str
    type: str  # "circle", "arrow", "text", "rectangle", "cone", "image", "zoom"
    start_time_ms: int
    end_time_ms: int  # -1 = fino alla fine
    data: Dict[str, Any]  # coordinate, colore, testo, etc.

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "start_time_ms": self.start_time_ms,
            "end_time_ms": self.end_time_ms,
            "data": self.data
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DrawingItem":
        return cls(**{k: v for k, v in d.items() if k in ("id", "type", "start_time_ms", "end_time_ms", "data")})


@dataclass
class PlaylistItem:
    """Elemento in una playlist."""
    clip_path: str
    start_ms: int
    end_ms: int
    label: str = ""
    event_id: Optional[str] = None  # id evento se clip creata con Inizio/Fine


class Project:
    """Progetto di analisi video."""
    
    def __init__(self):
        self.video_path: Optional[str] = None
        self.duration_ms: int = 0
        self.drawings: List[DrawingItem] = []
        self.playlist: List[PlaylistItem] = []
        self._drawing_counter = 0

    def add_drawing(self, drawing: DrawingItem) -> None:
        self._drawing_counter += 1
        drawing.id = drawing.id or f"draw_{self._drawing_counter}"
        self.drawings.append(drawing)

    def remove_drawing(self, drawing_id: str) -> bool:
        for i, d in enumerate(self.drawings):
            if d.id == drawing_id:
                self.drawings.pop(i)
                return True
        return False

    def get_drawings_at(self, timestamp_ms: int) -> List[DrawingItem]:
        return [
            d for d in self.drawings
            if d.start_time_ms <= timestamp_ms <= (d.end_time_ms if d.end_time_ms > 0 else 999999999)
        ]

    def add_to_playlist(self, item: PlaylistItem):
        self.playlist.append(item)

    def clear_playlist(self):
        self.playlist.clear()

    def remove_playlist_items_by_event_id(self, event_id: str) -> List[str]:
        """Rimuove dalla playlist i clip associati all'evento. Ritorna lista path dei file rimossi."""
        to_remove = [p for p in self.playlist if p.event_id == event_id]
        paths = [p.clip_path for p in to_remove]
        for p in to_remove:
            self.playlist.remove(p)
        return paths

    def to_dict(self) -> dict:
        return {
            "video_path": self.video_path,
            "duration_ms": self.duration_ms,
            "drawings": [d.to_dict() for d in self.drawings],
            "playlist": [
                {"clip_path": p.clip_path, "start_ms": p.start_ms, "end_ms": p.end_ms,
                 "label": p.label, "event_id": p.event_id}
                for p in self.playlist
            ]
        }

    def from_dict(self, d: dict):
        self.video_path = d.get("video_path")
        self.duration_ms = d.get("duration_ms", 0)
        self.drawings = [DrawingItem.from_dict(x) for x in d.get("drawings", [])]
        self.playlist = [
            PlaylistItem(
                c.get("clip_path", ""), c.get("start_ms", 0), c.get("end_ms", 0),
                c.get("label", ""), c.get("event_id")
            )
            for c in d.get("playlist", [])
        ]

    def save(self, path: str) -> bool:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    def load(self, path: str, events_data: Optional[dict] = None) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.from_dict(d)
            return True
        except Exception:
            return False
