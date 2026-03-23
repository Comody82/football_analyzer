"""
Dialog Statistiche: possesso %, passaggi, tiri, recuperi, pressing e metriche squadre/giocatori.
Dati da metrics.json e events_engine.json (dopo analisi automatica).
"""
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QScrollArea,
    QWidget,
)


def load_stats_from_project(project_analysis_dir: str):
    """Carica metriche e eventi dalla cartella progetto. Ritorna (metrics_dict, events_automatic_list) o (None, None)."""
    try:
        from analysis.config import get_analysis_output_path
        analysis_output = get_analysis_output_path(project_analysis_dir)
        metrics_path = analysis_output / "metrics.json"
        events_path = analysis_output / "detections" / "events_engine.json"
        metrics = None
        events_auto = []
        if metrics_path.exists():
            import json
            with open(metrics_path, "r", encoding="utf-8") as f:
                metrics = json.load(f)
        if events_path.exists():
            import json
            with open(events_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                events_auto = data.get("automatic", [])
        return metrics, events_auto
    except Exception:
        return None, []


class StatisticsDialog(QDialog):
    """Mostra possesso %, passaggi, tiri, recuperi, pressing e tabelle squadre/giocatori."""

    def __init__(self, project_analysis_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Statistiche")
        self.setMinimumSize(520, 480)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        metrics, events_auto = load_stats_from_project(project_analysis_dir)
        self._metrics = metrics or {}
        self._events_auto = events_auto or []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Riepilogo eventi automatici
        grp_events = QGroupBox("Eventi (analisi automatica)")
        ev_layout = QVBoxLayout(grp_events)
        counts = {}
        for e in self._events_auto:
            t = e.get("type", "event")
            counts[t] = counts.get(t, 0) + 1
        labels = {"pass": "Passaggi", "shot": "Tiri", "recovery": "Recuperi", "pressing": "Pressing"}
        for key, label in labels.items():
            ev_layout.addWidget(QLabel(f"{label}: {counts.get(key, 0)}"))
        layout.addWidget(grp_events)

        # Squadre
        teams = self._metrics.get("teams", [])
        if teams:
            grp_teams = QGroupBox("Squadre")
            teams_layout = QVBoxLayout(grp_teams)
            table = QTableWidget(len(teams), 3)
            table.setHorizontalHeaderLabels(["Squadra", "Possesso %", "Passaggi totali"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            for i, t in enumerate(teams):
                table.setItem(i, 0, QTableWidgetItem(f"Squadra {t.get('team_id', i)}"))
                table.setItem(i, 1, QTableWidgetItem(str(t.get("possession_pct", 0))))
                table.setItem(i, 2, QTableWidgetItem(str(t.get("passes_total", 0))))
            teams_layout.addWidget(table)
            layout.addWidget(grp_teams)

        # Giocatori (sintesi: primi 15)
        players = self._metrics.get("players", [])
        if players:
            grp_players = QGroupBox("Metriche giocatori (sintesi)")
            pl_layout = QVBoxLayout(grp_players)
            table = QTableWidget(min(15, len(players)), 5)
            table.setHorizontalHeaderLabels(["track_id", "team", "Distanza (m)", "Passaggi", "Tocchi"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            for i, p in enumerate(players[:15]):
                table.setItem(i, 0, QTableWidgetItem(str(p.get("track_id", ""))))
                table.setItem(i, 1, QTableWidgetItem(str(p.get("team", ""))))
                table.setItem(i, 2, QTableWidgetItem(str(p.get("distance_m", 0))))
                table.setItem(i, 3, QTableWidgetItem(str(p.get("passes", 0))))
                table.setItem(i, 4, QTableWidgetItem(str(p.get("touches", 0))))
            pl_layout.addWidget(table)
            if len(players) > 15:
                pl_layout.addWidget(QLabel(f"... e altri {len(players) - 15} giocatori"))
            layout.addWidget(grp_players)

        if not teams and not players and not self._events_auto:
            layout.addWidget(QLabel("Nessun dato disponibile. Esegui un'analisi automatica completa."))

        self.setStyleSheet("""
            QDialog { background: #1a2332; }
            QGroupBox { font-weight: bold; color: #e8f0fa; border: 1px solid #2a3f5f; border-radius: 6px; margin-top: 8px; padding-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
            QLabel { color: #c4d4e8; }
            QTableWidget { background: #0f172a; color: #e8f0fa; gridline-color: #334155; }
            QHeaderView::section { background: #334155; color: #e8f0fa; padding: 6px; }
        """)
