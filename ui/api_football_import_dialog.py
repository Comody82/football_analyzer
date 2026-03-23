"""
Dialog per importare squadre e giocatori da API-Football (api-sports.io).
Flusso: API key → cerca squadra → anteprima giocatori → importa nel registry.
"""
import json
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QComboBox,
    QProgressBar, QWidget, QSplitter, QFrame
)

API_KEY_FILE = Path(__file__).parent.parent / "data" / "api_keys.json"
API_BASE = "https://v3.football.api-sports.io"

POSITION_MAP = {
    "Goalkeeper": "Portiere",
    "Defender": "Difensore",
    "Midfielder": "Centrocampista",
    "Attacker": "Attaccante",
}

CURRENT_YEAR = 2024


def _load_api_key() -> str:
    if API_KEY_FILE.exists():
        try:
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("api_football", "")
        except Exception:
            pass
    return ""


def _save_api_key(key: str):
    API_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if API_KEY_FILE.exists():
        try:
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data["api_football"] = key
    with open(API_KEY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _api_get(endpoint: str, params: dict, key: str) -> dict:
    url = f"{API_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"x-apisports-key": key})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


class _SearchWorker(QThread):
    result = pyqtSignal(list, str)  # (teams_list, error_msg)

    def __init__(self, query: str, api_key: str):
        super().__init__()
        self.query = query
        self.api_key = api_key

    def run(self):
        try:
            data = _api_get("teams", {"name": self.query}, self.api_key)
            teams = data.get("response", [])
            self.result.emit(teams, "")
        except Exception as e:
            self.result.emit([], str(e))


class _PlayersWorker(QThread):
    result = pyqtSignal(list, str)  # (players_list, error_msg)

    def __init__(self, team_id: int, season: int, api_key: str):
        super().__init__()
        self.team_id = team_id
        self.season = season
        self.api_key = api_key

    def run(self):
        try:
            all_players = []
            page = 1
            while True:
                data = _api_get(
                    "players",
                    {"team": self.team_id, "season": self.season, "page": page},
                    self.api_key
                )
                resp = data.get("response", [])
                all_players.extend(resp)
                paging = data.get("paging", {})
                if page >= paging.get("total", 1):
                    break
                page += 1
            self.result.emit(all_players, "")
        except Exception as e:
            self.result.emit([], str(e))


class ApiFootballImportDialog(QDialog):
    """Importa squadra e giocatori da API-Football nel registry PRELYT."""

    def __init__(self, teams_repo, parent=None):
        super().__init__(parent)
        self.teams_repo = teams_repo
        self._selected_team_data = None   # {id, name, logo, country}
        self._players_data = []            # lista raw API
        self._search_worker: Optional[_SearchWorker] = None
        self._players_worker: Optional[_PlayersWorker] = None
        self.setWindowTitle("Importa da API-Football")
        self.setMinimumSize(760, 540)
        self.resize(860, 580)
        self._build_ui()
        self._apply_style()

    # ─────────────────────────────────── UI ────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # ── Header ──
        hdr = QHBoxLayout()
        title = QLabel("🌐 Importa da API-Football")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #f1f6ff;")
        hdr.addWidget(title, 1)
        lbl_link = QLabel('<a href="https://dashboard.api-football.com" '
                          'style="color:#2ed8a3;">Ottieni API key</a>')
        lbl_link.setOpenExternalLinks(True)
        lbl_link.setStyleSheet("font-size: 11px;")
        hdr.addWidget(lbl_link, 0)
        root.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: rgba(255,255,255,0.08);")
        root.addWidget(sep)

        # ── API Key row ──
        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("API Key:"))
        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("Incolla qui la tua API key di api-sports.io")
        self._key_input.setEchoMode(QLineEdit.Password)
        self._key_input.setText(_load_api_key())
        key_row.addWidget(self._key_input, 1)
        btn_show = QPushButton("👁")
        btn_show.setFixedSize(28, 28)
        btn_show.setCheckable(True)
        btn_show.toggled.connect(
            lambda c: self._key_input.setEchoMode(QLineEdit.Normal if c else QLineEdit.Password)
        )
        key_row.addWidget(btn_show)
        root.addLayout(key_row)

        # ── Search row ──
        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Cerca squadra per nome (es. Milan, Roma, Juventus...)")
        self._search_input.returnPressed.connect(self._on_search)
        search_row.addWidget(self._search_input, 1)
        self._season_combo = QComboBox()
        for y in range(2024, 2018, -1):
            self._season_combo.addItem(str(y), y)
        self._season_combo.setFixedWidth(80)
        search_row.addWidget(self._season_combo)
        btn_search = QPushButton("🔍 Cerca")
        btn_search.setFixedHeight(32)
        btn_search.clicked.connect(self._on_search)
        search_row.addWidget(btn_search)
        root.addLayout(search_row)

        # ── Progress bar ──
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(4)
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        # ── Splitter: risultati sx | giocatori dx ──
        splitter = QSplitter(Qt.Horizontal)

        # Lista squadre risultato
        teams_panel = QWidget()
        tv = QVBoxLayout(teams_panel)
        tv.setContentsMargins(0, 0, 6, 0)
        tv.setSpacing(4)
        tv.addWidget(QLabel("Risultati ricerca:"))
        self._teams_list = QListWidget()
        self._teams_list.itemClicked.connect(self._on_team_selected)
        tv.addWidget(self._teams_list, 1)
        splitter.addWidget(teams_panel)

        # Pannello giocatori
        players_panel = QWidget()
        pv = QVBoxLayout(players_panel)
        pv.setContentsMargins(6, 0, 0, 0)
        pv.setSpacing(4)

        ph = QHBoxLayout()
        self._lbl_players_title = QLabel("Seleziona una squadra →")
        self._lbl_players_title.setStyleSheet("font-weight: 600; color: #e8f0fa;")
        ph.addWidget(self._lbl_players_title, 1)
        pv.addLayout(ph)

        self._players_table = QTableWidget()
        self._players_table.setColumnCount(3)
        self._players_table.setHorizontalHeaderLabels(["#", "Nome", "Ruolo"])
        self._players_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._players_table.verticalHeader().setVisible(False)
        self._players_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._players_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._players_table.setAlternatingRowColors(True)
        self._players_table.setColumnWidth(0, 44)
        self._players_table.setColumnWidth(2, 130)
        pv.addWidget(self._players_table, 1)
        splitter.addWidget(players_panel)

        splitter.setSizes([260, 480])
        root.addWidget(splitter, 1)

        # ── Info free tier ──
        info = QLabel("ℹ️  Piano Free: 100 richieste/giorno. "
                      "Ogni ricerca usa 1 req; caricare giocatori usa 1+ req.")
        info.setStyleSheet("font-size: 10px; color: #7a92b0;")
        root.addWidget(info)

        # ── Footer buttons ──
        footer = QHBoxLayout()
        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet("font-size: 11px; color: #9eb0c8;")
        footer.addWidget(self._lbl_status, 1)
        btn_close = QPushButton("Chiudi")
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.reject)
        footer.addWidget(btn_close)
        self._btn_import = QPushButton("✅ Importa Squadra")
        self._btn_import.setFixedHeight(32)
        self._btn_import.setEnabled(False)
        self._btn_import.clicked.connect(self._on_import)
        footer.addWidget(self._btn_import)
        root.addLayout(footer)

    # ─────────────────────────────── Logic ─────────────────────────────────

    def _on_search(self):
        key = self._key_input.text().strip()
        if not key:
            QMessageBox.warning(self, "API Key mancante",
                                "Inserisci la tua API key di api-sports.io.")
            return
        query = self._search_input.text().strip()
        if len(query) < 3:
            QMessageBox.warning(self, "Ricerca",
                                "Inserisci almeno 3 caratteri per cercare.")
            return
        _save_api_key(key)
        self._set_loading(True)
        self._teams_list.clear()
        self._players_table.setRowCount(0)
        self._selected_team_data = None
        self._btn_import.setEnabled(False)
        self._search_worker = _SearchWorker(query, key)
        self._search_worker.result.connect(self._on_search_result)
        self._search_worker.start()

    def _on_search_result(self, teams: list, error: str):
        self._set_loading(False)
        if error:
            self._lbl_status.setText(f"❌ Errore: {error}")
            return
        if not teams:
            self._lbl_status.setText("Nessuna squadra trovata.")
            return
        self._lbl_status.setText(f"{len(teams)} squadr{'a' if len(teams)==1 else 'e'} trovata/e")
        for entry in teams:
            t = entry.get("team", {})
            v = entry.get("venue", {})
            text = f"{t.get('name', '?')}   •   {t.get('country', '')}   •   {v.get('city', '')}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, {
                "id": t.get("id"),
                "name": t.get("name", ""),
                "logo": t.get("logo", ""),
                "country": t.get("country", ""),
            })
            self._teams_list.addItem(item)

    def _on_team_selected(self, item: QListWidgetItem):
        self._selected_team_data = item.data(Qt.UserRole)
        name = self._selected_team_data["name"]
        self._lbl_players_title.setText(f"Caricamento giocatori di {name}...")
        self._players_table.setRowCount(0)
        self._btn_import.setEnabled(False)
        self._set_loading(True)
        season = self._season_combo.currentData()
        key = self._key_input.text().strip()
        self._players_worker = _PlayersWorker(
            self._selected_team_data["id"], season, key
        )
        self._players_worker.result.connect(self._on_players_result)
        self._players_worker.start()

    def _on_players_result(self, players: list, error: str):
        self._set_loading(False)
        if error:
            self._lbl_status.setText(f"❌ Errore caricamento giocatori: {error}")
            return
        self._players_data = players
        name = self._selected_team_data["name"] if self._selected_team_data else "?"
        # Estrai lega dalla prima statistica disponibile
        if players and self._selected_team_data:
            first_stats = players[0].get("statistics", [{}])[0] if players else {}
            league_info = first_stats.get("league", {})
            self._selected_team_data["league"] = league_info.get("name", "")
            # Aggiorna country se non già presente
            if not self._selected_team_data.get("country"):
                self._selected_team_data["country"] = league_info.get("country", "")
        self._lbl_players_title.setText(
            f"{name}  •  {len(players)} giocatori"
        )
        self._players_table.setRowCount(len(players))
        for row, entry in enumerate(players):
            p = entry.get("player", {})
            stats = entry.get("statistics", [{}])[0] if entry.get("statistics") else {}
            games = stats.get("games", {})

            jersey = games.get("number")
            pos_en = games.get("position") or p.get("position") or ""
            pos_it = POSITION_MAP.get(pos_en, "Non specificato")

            self._players_table.setItem(row, 0,
                QTableWidgetItem(str(jersey) if jersey else ""))
            self._players_table.setItem(row, 1,
                QTableWidgetItem(p.get("name", "")))
            self._players_table.setItem(row, 2,
                QTableWidgetItem(pos_it))
        self._btn_import.setEnabled(True)
        self._lbl_status.setText(
            f"✅ {len(players)} giocatori pronti — clicca 'Importa Squadra' per salvare."
        )

    def _on_import(self):
        if not self._selected_team_data or not self._players_data:
            return

        # Verifica se squadra già esiste
        team_name = self._selected_team_data["name"]
        existing = next(
            (t for t in self.teams_repo.list_teams() if t.name == team_name), None
        )
        if existing:
            ans = QMessageBox.question(
                self, "Squadra già presente",
                f"'{team_name}' è già nel registro.\nVuoi aggiungere comunque i giocatori?",
                QMessageBox.Yes | QMessageBox.No
            )
            if ans == QMessageBox.No:
                return
            team = existing
        else:
            logo = self._selected_team_data.get("logo") or None
            team = self.teams_repo.add_team(
                name=team_name,
                logo_path=logo,
                country=self._selected_team_data.get("country", ""),
                league=self._selected_team_data.get("league", ""),
            )

        # Importa giocatori
        imported = 0
        skipped = 0
        existing_jerseys = {p.jersey_number for p in team.players if p.jersey_number}

        for entry in self._players_data:
            p = entry.get("player", {})
            stats = entry.get("statistics", [{}])[0] if entry.get("statistics") else {}
            games = stats.get("games", {})
            name = p.get("name", "").strip()
            if not name:
                continue
            jersey_raw = games.get("number")
            try:
                jersey = int(jersey_raw) if jersey_raw is not None else None
            except (ValueError, TypeError):
                jersey = None
            pos_en = games.get("position") or p.get("position") or ""
            pos_it = POSITION_MAP.get(pos_en, "Non specificato")

            # Salta duplicati per numero maglia
            if jersey and jersey in existing_jerseys:
                skipped += 1
                continue

            self.teams_repo.add_player(
                team_id=team.id,
                name=name,
                jersey_number=jersey,
                role=pos_it,
            )
            if jersey:
                existing_jerseys.add(jersey)
            imported += 1

        msg = f"✅ Importati {imported} giocatori in '{team_name}'."
        if skipped:
            msg += f"\n{skipped} saltati (numero maglia già presente)."
        QMessageBox.information(self, "Importazione completata", msg)
        self.accept()

    # ─────────────────────────────── Helpers ───────────────────────────────

    def _set_loading(self, loading: bool):
        self._progress.setVisible(loading)
        if loading:
            self._lbl_status.setText("⏳ Caricamento...")

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background: #0d1929; color: #d0dff0; }
            QLabel { color: #d0dff0; font-size: 12px; }
            QLineEdit, QComboBox {
                background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px; padding: 6px 10px; color: #e8f0fa; font-size: 12px;
            }
            QListWidget {
                background: rgba(11,19,35,0.7); border: 1px solid rgba(255,255,255,0.08);
                border-radius: 8px; color: #d0dff0; font-size: 12px;
            }
            QListWidget::item { padding: 6px 8px; }
            QListWidget::item:selected { background: rgba(46,216,163,0.2); }
            QListWidget::item:hover { background: rgba(255,255,255,0.06); }
            QTableWidget {
                background: rgba(11,19,35,0.6); border: 1px solid rgba(255,255,255,0.08);
                border-radius: 8px; gridline-color: rgba(255,255,255,0.05);
                color: #d8e8f8; font-size: 12px;
            }
            QTableWidget::item { padding: 4px 8px; }
            QTableWidget::item:alternate { background: rgba(255,255,255,0.02); }
            QTableWidget::item:selected { background: rgba(46,216,163,0.18); }
            QHeaderView::section {
                background: rgba(11,19,35,0.9); color: #9eb0c8;
                border: none; padding: 6px 8px; font-size: 11px; font-weight: 600;
            }
            QPushButton {
                background: rgba(255,255,255,0.08); color: #d0dff0;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px; padding: 0 14px; font-size: 12px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.14); }
            QPushButton#import_btn {
                background: #17806a; color: #eafff8; border: none; font-weight: 700;
            }
            QPushButton#import_btn:hover { background: #1e947c; }
            QPushButton#import_btn:disabled { background: rgba(23,128,106,0.3); color: #5a9080; }
            QProgressBar { border: none; background: rgba(255,255,255,0.05); border-radius: 2px; }
            QProgressBar::chunk { background: #2ed8a3; border-radius: 2px; }
        """)
        self._btn_import.setObjectName("import_btn")
