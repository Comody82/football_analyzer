"""
Dialog per collegare le squadre rilevate dall'IA (team 0 / team 1)
a nomi e colori reali definiti dall'utente.
"""
import json
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPixmap, QIcon
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QColorDialog, QFrame, QMessageBox, QWidget,
)

from team_links import ProjectTeamLinks


class _TeamRow(QWidget):
    """Riga per configurare una squadra: campione colore + campo nome."""

    def __init__(self, team_idx: int, team_links: ProjectTeamLinks, parent=None):
        super().__init__(parent)
        self._team_idx  = team_idx
        self._color     = team_links.get_color(team_idx)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Etichetta squadra
        lbl = QLabel(f"Squadra {team_idx}:")
        lbl.setFixedWidth(80)
        lbl.setStyleSheet("color: #c8d8ec; font-size: 12px; font-weight: 600;")
        layout.addWidget(lbl)

        # Pulsante colore
        self._btn_color = QPushButton()
        self._btn_color.setFixedSize(36, 36)
        self._btn_color.setToolTip("Clicca per cambiare colore maglia")
        self._btn_color.clicked.connect(self._pick_color)
        self._refresh_color_btn()
        layout.addWidget(self._btn_color)

        # Campo nome
        self._edit_name = QLineEdit()
        self._edit_name.setText(team_links.get_name(team_idx))
        self._edit_name.setPlaceholderText(f"Nome squadra {team_idx}")
        self._edit_name.setStyleSheet(
            "background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15);"
            "border-radius: 6px; color: #e8f4ff; padding: 5px 10px; font-size: 13px;")
        layout.addWidget(self._edit_name, 1)

    def _pick_color(self):
        col = QColorDialog.getColor(QColor(self._color), self, "Colore maglia")
        if col.isValid():
            self._color = col.name()
            self._refresh_color_btn()

    def _refresh_color_btn(self):
        self._btn_color.setStyleSheet(
            f"background: {self._color}; border: 2px solid rgba(255,255,255,0.3);"
            f"border-radius: 6px;")

    def get_name(self) -> str:
        return self._edit_name.text().strip()

    def get_color(self) -> str:
        return self._color


class TeamLinksDialog(QDialog):
    """
    Dialog per assegnare nome e colore maglia alle squadre rilevate dall'IA.

    Uso:
        dlg = TeamLinksDialog(project_dir, team_links, parent=self)
        dlg.exec_()
        # team_links è già aggiornato e salvato dopo exec_()
    """

    def __init__(self, project_dir: str, team_links: ProjectTeamLinks, parent=None):
        super().__init__(parent)
        self._project_dir = project_dir
        self._team_links  = team_links

        self.setWindowTitle("Collega Squadre")
        self.setMinimumWidth(480)
        self.setStyleSheet("""
            QDialog  { background: #0d1b2e; color: #e8f0fa; }
            QLabel   { color: #c8d8ec; font-size: 12px; }
            QPushButton {
                background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px; color: #e8f4ff; font-size: 12px; font-weight: 600;
                padding: 6px 16px; min-height: 28px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.13); }
            QPushButton#btnSave {
                background: #17806a; border: none; color: #eafff8; font-weight: 700;
            }
            QPushButton#btnSave:hover { background: #1e947c; }
            QFrame#sep { background: rgba(255,255,255,0.08); }
        """)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        # Titolo
        title = QLabel("Collega Squadre")
        title.setStyleSheet("font-size: 17px; font-weight: 700; color: #f1f6ff;")
        root.addWidget(title)

        sub = QLabel(
            "Assegna un nome e un colore maglia alle squadre rilevate automaticamente dall'IA.\n"
            "Questi dati vengono usati nelle statistiche e nel report.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #6a8aaa; font-size: 11px;")
        root.addWidget(sub)

        sep = QFrame()
        sep.setObjectName("sep")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # Riga squadra 0
        self._row0 = _TeamRow(0, self._team_links)
        root.addWidget(self._row0)

        # Riga squadra 1
        self._row1 = _TeamRow(1, self._team_links)
        root.addWidget(self._row1)

        # Hint colori rilevati dall'analisi
        self._lbl_hint = QLabel("")
        self._lbl_hint.setWordWrap(True)
        self._lbl_hint.setStyleSheet("color: #4a6a8a; font-size: 10px;")
        root.addWidget(self._lbl_hint)
        self._try_load_detected_colors()

        root.addStretch()

        sep2 = QFrame()
        sep2.setObjectName("sep")
        sep2.setFrameShape(QFrame.HLine)
        sep2.setFixedHeight(1)
        root.addWidget(sep2)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annulla")
        btn_cancel.clicked.connect(self.reject)
        self._btn_save = QPushButton("💾  Salva")
        self._btn_save.setObjectName("btnSave")
        self._btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_save)
        root.addLayout(btn_row)

    def _try_load_detected_colors(self):
        """
        Prova a leggere i colori maglia rilevati dall'analisi (player_tracks.json).
        Se disponibili, li mostra come suggerimento e li usa come default.
        """
        try:
            from analysis.config import get_analysis_output_path
            tracks_path = Path(get_analysis_output_path(self._project_dir)) / "player_tracks.json"
            if not tracks_path.exists():
                return
            with open(tracks_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            colors = data.get("team_colors", {})
            if colors:
                hints = []
                for k, v in colors.items():
                    hints.append(f"Team {k}: {v}")
                self._lbl_hint.setText(
                    "Colori rilevati dall'IA: " + "  |  ".join(hints) +
                    "\nModifica i colori sopra per farli corrispondere alle maglie reali.")
        except Exception:
            pass

    def _save(self):
        name0 = self._row0.get_name()
        name1 = self._row1.get_name()
        if not name0 or not name1:
            QMessageBox.warning(self, "Dati mancanti", "Inserisci il nome di entrambe le squadre.")
            return
        self._team_links.set_team(0, name0, self._row0.get_color())
        self._team_links.set_team(1, name1, self._row1.get_color())
        self._team_links.save()
        self.accept()
