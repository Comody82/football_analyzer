"""Dialog di configurazione dei pulsanti evento."""
import json
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QLineEdit,
    QWidget,
    QCheckBox,
    QDialogButtonBox,
    QMessageBox,
    QColorDialog,
    QScrollArea,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from core.events import EventType
from config import DEFAULT_EVENT_TYPES, get_event_buttons_config_path


def load_saved_event_types():
    """Carica i tipi evento salvati come configurazione predefinita, o None se non esiste."""
    path = get_event_buttons_config_path()
    if not Path(path).exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("as_default"):
            return None
        return [EventType.from_dict(t) for t in data.get("event_types", [])]
    except (json.JSONDecodeError, IOError):
        return None


def save_event_types_as_default(event_types: list) -> bool:
    """Salva i tipi evento come configurazione predefinita persistente."""
    path = get_event_buttons_config_path()
    try:
        data = {
            "as_default": True,
            "event_types": [t.to_dict() for t in event_types],
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except IOError:
        return False


def clear_default_config() -> bool:
    """Rimuove la configurazione predefinita salvata."""
    path = get_event_buttons_config_path()
    try:
        if Path(path).exists():
            Path(path).unlink()
        return True
    except OSError:
        return False


class _EventTypeRow(QWidget):
    """Riga singola nella lista configurazione: nome, colore, elimina."""

    def __init__(self, event_type: EventType, on_delete=None, parent=None):
        super().__init__(parent)
        self._event_type = event_type
        self._on_delete = on_delete
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nome")
        self.name_edit.setText(event_type.name)
        self.name_edit.setMinimumWidth(120)
        self.name_edit.setMaximumWidth(180)
        layout.addWidget(self.name_edit)
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(28, 28)
        self.color_btn.setStyleSheet(f"background-color: {event_type.color}; border: 1px solid #555;")
        self.color_btn.clicked.connect(self._pick_color)
        layout.addWidget(self.color_btn)
        self._color = event_type.color
        delete_btn = QPushButton("Elimina")
        delete_btn.setFixedWidth(90)
        delete_btn.clicked.connect(lambda: on_delete(self) if on_delete else None)
        layout.addWidget(delete_btn)
        layout.addStretch()

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._color), self)
        if c.isValid():
            self._color = c.name()
            self.color_btn.setStyleSheet(f"background-color: {self._color}; border: 1px solid #555;")

    def get_event_type(self) -> EventType:
        """Ritorna l'EventType aggiornato con i valori della riga."""
        return EventType(
            id=self._event_type.id,
            name=self.name_edit.text().strip() or self._event_type.name,
            icon="•",
            color=self._color,
        )


class EventButtonsConfigDialog(QDialog):
    """Finestra di configurazione dei pulsanti evento."""

    def __init__(self, event_types: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurazione pulsanti evento")
        self.setMinimumSize(480, 420)
        self._initial_types = [EventType(t.id, t.name, t.icon, t.color) for t in event_types]
        self._rows: list[_EventTypeRow] = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Modifica i nomi, aggiungi o elimina pulsanti evento:"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(2)
        scroll.setWidget(self.list_container)
        layout.addWidget(scroll, 1)

        for et in self._initial_types:
            self._add_row(et)

        add_btn = QPushButton("➕ Aggiungi pulsante personalizzato")
        add_btn.setProperty("accent", True)
        add_btn.clicked.connect(self._add_new_custom)
        layout.addWidget(add_btn)

        self.save_as_default_cb = QCheckBox("Imposta come configurazione predefinita")
        self.save_as_default_cb.setToolTip(
            "Se attivo, i pulsanti vengono salvati. Alla riapertura del programma resteranno come configurati. "
            "Se non attivo, le modifiche valgono solo per questa sessione."
        )
        layout.addWidget(self.save_as_default_cb)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _add_row(self, event_type: EventType):
        row = _EventTypeRow(event_type, on_delete=self._on_delete_row)
        self._rows.append(row)
        self.list_layout.addWidget(row)

    def _on_delete_row(self, row: _EventTypeRow):
        self._rows.remove(row)
        row.deleteLater()

    def _add_new_custom(self):
        """Aggiunge un nuovo pulsante personalizzato."""
        base_id = "custom_nuovo"
        n = 1
        existing_ids = {r._event_type.id for r in self._rows}
        while f"{base_id}_{n}" in existing_ids:
            n += 1
        tid = f"{base_id}_{n}"  # custom_nuovo_1, custom_nuovo_2, ...
        et = EventType(id=tid, name="Nuovo", icon="•", color="#9CA3AF")
        self._add_row(et)

    def get_event_types(self) -> list:
        """Ritorna la lista di EventType aggiornata dai campi della finestra."""
        return [r.get_event_type() for r in self._rows]

    def save_as_default(self) -> bool:
        return self.save_as_default_cb.isChecked()
