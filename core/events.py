"""Gestione eventi e tipi di evento."""
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Any, Dict
import json


@dataclass
class EventType:
    """Tipo di evento (predefinito o custom)."""
    id: str
    name: str
    icon: str = "•"
    color: str = "#FFFFFF"

    def to_dict(self):
        return {"id": self.id, "name": self.name, "icon": self.icon, "color": self.color}

    @classmethod
    def from_dict(cls, d: dict) -> "EventType":
        return cls(**{k: v for k, v in d.items() if k in ("id", "name", "icon", "color")})


@dataclass
class Event:
    """Singolo evento annotato nel video."""
    id: str
    event_type_id: str
    timestamp_ms: int
    description: str = ""
    team: Optional[str] = None  # "home" o "away" per statistiche
    label: Optional[str] = None  # nome personalizzato per l'evento (editabile inline)
    drawing_id: Optional[str] = None  # id del disegno in Project.drawings (backward compat)
    annotations: List[Dict[str, Any]] = field(default_factory=list)  # cerchi, frecce, testo, ecc.

    def to_dict(self):
        return {
            "id": self.id,
            "event_type_id": self.event_type_id,
            "timestamp_ms": self.timestamp_ms,
            "description": self.description,
            "team": self.team,
            "label": self.label,
            "drawing_id": self.drawing_id,
            "annotations": self.annotations,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        allow = ("id", "event_type_id", "timestamp_ms", "description", "team", "label", "drawing_id", "annotations")
        kwargs = {k: v for k, v in d.items() if k in allow}
        if "annotations" not in kwargs:
            kwargs["annotations"] = []
        return cls(**kwargs)


class EventManager:
    """Gestisce eventi e tipi di evento."""
    
    def __init__(self):
        self._event_types: List[EventType] = []
        self._events: List[Event] = []
        self._event_counter = 0
        self._on_change: Optional[Callable] = None

    def set_on_change(self, callback: Callable):
        self._on_change = callback

    def _notify(self):
        if self._on_change:
            self._on_change()

    def load_default_types(self, default_types: List[dict]):
        """Carica tipi predefiniti."""
        self._event_types = [EventType.from_dict(t) for t in default_types]

    def add_event_type(self, event_type: EventType) -> bool:
        """Aggiunge un tipo personalizzato."""
        if any(t.id == event_type.id for t in self._event_types):
            return False
        self._event_types.append(event_type)
        self._notify()
        return True

    def update_event_type_name(self, type_id: str, new_name: str) -> bool:
        """Modifica il nome di un tipo di evento."""
        evt = next((t for t in self._event_types if t.id == type_id), None)
        if not evt or not new_name.strip():
            return False
        updated = EventType(id=evt.id, name=new_name.strip(), icon=evt.icon, color=evt.color)
        idx = self._event_types.index(evt)
        self._event_types[idx] = updated
        self._notify()
        return True

    def update_event_type_full(
        self, type_id: str, name: str = None, icon: str = None, color: str = None
    ) -> bool:
        """Modifica nome, icona e/o colore di un tipo di evento."""
        evt = next((t for t in self._event_types if t.id == type_id), None)
        if not evt:
            return False
        new_name = name.strip() if name and name.strip() else evt.name
        new_icon = icon if icon else evt.icon
        new_color = color if color else evt.color
        updated = EventType(id=evt.id, name=new_name, icon=new_icon, color=new_color)
        idx = self._event_types.index(evt)
        self._event_types[idx] = updated
        self._notify()
        return True

    def load_event_types(self, types: List[EventType]) -> None:
        """Sostituisce tutti i tipi di evento con la lista fornita."""
        self._event_types = list(types)
        self._notify()

    def remove_event_type(self, type_id: str) -> bool:
        """Rimuove un tipo di evento. Deve restare almeno un tipo."""
        evt = next((t for t in self._event_types if t.id == type_id), None)
        if not evt:
            return False
        if len(self._event_types) <= 1:
            return False
        self._event_types.remove(evt)
        self._events = [e for e in self._events if e.event_type_id != type_id]
        self._notify()
        return True

    def get_event_types(self) -> List[EventType]:
        return self._event_types.copy()

    def get_event_type(self, type_id: str) -> Optional[EventType]:
        return next((t for t in self._event_types if t.id == type_id), None)

    def add_event(
        self,
        event_type_id: str,
        timestamp_ms: int,
        description: str = "",
        team: Optional[str] = None,
        label: Optional[str] = None,
        drawing_id: Optional[str] = None,
        annotations: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Event]:
        """Aggiunge un evento."""
        if not self.get_event_type(event_type_id):
            return None
        self._event_counter += 1
        evt = Event(
            id=f"evt_{self._event_counter}",
            event_type_id=event_type_id,
            timestamp_ms=timestamp_ms,
            description=description,
            team=team,
            label=label,
            drawing_id=drawing_id,
            annotations=annotations or [],
        )
        self._events.append(evt)
        self._events.sort(key=lambda e: e.timestamp_ms)
        self._notify()
        return evt

    def remove_event(self, event_id: str) -> bool:
        evt = next((e for e in self._events if e.id == event_id), None)
        if evt:
            self._events.remove(evt)
            self._notify()
            return True
        return False

    def update_event_description(self, event_id: str, description: str) -> bool:
        """Aggiorna la descrizione di un evento."""
        evt = next((e for e in self._events if e.id == event_id), None)
        if evt:
            evt.description = description
            return True
        return False

    def update_event_label(self, event_id: str, label: str) -> bool:
        """Aggiorna il nome/label di un evento."""
        evt = next((e for e in self._events if e.id == event_id), None)
        if evt:
            evt.label = label.strip() if label else None
            self._notify()
            return True
        return False

    def _next_default_event_label(self) -> str:
        """Genera il prossimo nome default (Evento 1, Evento 2, ...)."""
        used = set()
        for e in self._events:
            if e.label and e.label.startswith("Evento "):
                try:
                    n = int(e.label[7:].strip())
                    used.add(n)
                except ValueError:
                    pass
        n = 1
        while n in used:
            n += 1
        return f"Evento {n}"

    def update_event_type(self, event_id: str, new_type_id: str) -> bool:
        """Aggiorna il tipo (nome) di un evento."""
        if not self.get_event_type(new_type_id):
            return False
        evt = next((e for e in self._events if e.id == event_id), None)
        if evt:
            evt.event_type_id = new_type_id
            self._notify()
            return True
        return False

    def get_events(self) -> List[Event]:
        return self._events.copy()

    def get_events_by_type(self, type_id: str) -> List[Event]:
        return [e for e in self._events if e.event_type_id == type_id]

    def get_annotazione_event_at_timestamp(self, timestamp_ms: int) -> Optional[Event]:
        """Ritorna l'evento annotazione al timestamp esatto, se esiste."""
        return next(
            (e for e in self._events if e.event_type_id == "annotazione" and e.timestamp_ms == timestamp_ms),
            None
        )

    def get_event_at_timestamp(
        self, timestamp_ms: int, tolerance_ms: int = 500
    ) -> Optional[Event]:
        """Ritorna l'evento al timestamp (o entro tolerance_ms per piccoli scarti di frame)."""
        exact = next((e for e in self._events if e.timestamp_ms == timestamp_ms), None)
        if exact:
            return exact
        if tolerance_ms <= 0:
            return None
        candidates = [
            e for e in self._events
            if abs(e.timestamp_ms - timestamp_ms) <= tolerance_ms
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda e: abs(e.timestamp_ms - timestamp_ms))

    def add_annotation_to_event(self, event_id: str, annotation_data: dict) -> bool:
        """Aggiunge un'annotazione a un evento esistente."""
        evt = next((e for e in self._events if e.id == event_id), None)
        if not evt:
            return False
        evt.annotations.append(annotation_data)
        self._notify()
        return True

    def update_annotation_in_event(self, event_id: str, ann_index: int, annotation_data: dict) -> bool:
        """Aggiorna un'annotazione esistente (dopo move/resize)."""
        evt = next((e for e in self._events if e.id == event_id), None)
        if not evt or ann_index < 0 or ann_index >= len(evt.annotations):
            return False
        evt.annotations[ann_index] = annotation_data
        self._notify()
        return True

    def remove_annotation_from_event(self, event_id: str, ann_index: int) -> bool:
        """Rimuove un'annotazione da un evento."""
        evt = next((e for e in self._events if e.id == event_id), None)
        if not evt or ann_index < 0 or ann_index >= len(evt.annotations):
            return False
        evt.annotations.pop(ann_index)
        if not evt.annotations:
            self.remove_event(event_id)
        else:
            self._notify()
        return True

    def clear_events(self):
        self._events.clear()
        self._notify()

    def to_dict(self) -> dict:
        return {
            "event_types": [t.to_dict() for t in self._event_types],
            "events": [e.to_dict() for e in self._events],
            "counter": self._event_counter
        }

    def from_dict(self, d: dict):
        self._event_types = [EventType.from_dict(t) for t in d.get("event_types", [])]
        self._events = [Event.from_dict(e) for e in d.get("events", [])]
        self._event_counter = d.get("counter", 0)
        self._notify()
