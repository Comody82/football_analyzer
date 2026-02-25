"""Configurazione dell'applicazione Football Analyzer."""
import os

# Percorsi
APP_NAME = "Football Analyzer"
HIGHLIGHTS_FOLDER = "Highlights"
PROJECT_EXTENSION = ".fap"


def get_event_buttons_config_path() -> str:
    """Percorso del file di configurazione persistente dei pulsanti evento."""
    if os.name == "nt":
        base = os.getenv("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~/.config")
    dir_path = os.path.join(base, APP_NAME)
    os.makedirs(dir_path, exist_ok=True)
    return os.path.join(dir_path, "event_buttons.json")

# Eventi predefiniti
DEFAULT_EVENT_TYPES = [
    {"id": "goal", "name": "Gol", "icon": "⚽", "color": "#22C55E"},
    {"id": "shot_on", "name": "Tiro in Porta", "icon": "🎯", "color": "#3B82F6"},
    {"id": "shot_off", "name": "Tiro Fuori", "icon": "🚫", "color": "#EF4444"},
    {"id": "corner", "name": "Corner", "icon": "🟨", "color": "#F59E0B"},
    {"id": "pass", "name": "Passaggio", "icon": "↔️", "color": "#8B5CF6"},
    {"id": "evento", "name": "Evento", "icon": "📌", "color": "#9CA3AF"},  # tipo generico per "Crea Evento"
]

# Colori per disegno
DRAW_COLORS = [
    "#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF",
    "#FFFFFF", "#FFA500", "#800080", "#008000", "#FFC0CB", "#A52A2A"
]

# Secondi predefiniti per clip
DEFAULT_CLIP_PRE_SECONDS = 5
DEFAULT_CLIP_POST_SECONDS = 5

# Freeze frame al disegno (secondi)
FREEZE_DURATION_SECONDS = 3
