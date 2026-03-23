# Fase 5 – Soglie e parametri (event engine e metriche)

Parametri configurabili per possesso, cambio possesso e eventi automatici (passaggio, recupero, tiro, pressing). Stesso file di config e stesso modulo condiviso per **analisi locale** e **backend cloud**.

---

## Step 5.1 – Soglie di distanza e possesso

### File di configurazione

- **Percorso**: `config/event_engine_params.json` (rispetto alla root del progetto).
- Se il file non esiste o è incompleto, il modulo `analysis.event_engine_params` usa i **valori di default** definiti in codice (stessi del JSON di esempio).

### Parametri possesso

| Chiave | Tipo | Default | Descrizione |
|--------|------|---------|-------------|
| `possession.max_ball_player_distance_m` | number | 2.0 | Distanza massima palla–giocatore (metri) per considerare il giocatore in possesso. |
| `possession.min_possession_time_s` | number | 0.5 | Tempo minimo (secondi) per conteggiare un possesso valido (evita flicker). |
| `possession.change_possession_on_opponent_control` | boolean | true | Se true, il cambio possesso avviene quando un avversario entra in “controllo” (sotto la distanza massima). |
| `possession.change_possession_distance_m` | number | 2.0 | Distanza usata per stabilire il controllo nella logica di cambio possesso (può coincidere con `max_ball_player_distance_m`). |

### Uso nel modulo condiviso

```python
from analysis.event_engine_params import get_params, get_possession_params

p = get_params()
max_dist = p["possession"]["max_ball_player_distance_m"]
min_time = p["possession"]["min_possession_time_s"]

# oppure
possession = get_possession_params()
max_dist = possession["max_ball_player_distance_m"]
```

---

## Step 5.2 – Parametri evento

### Passaggio

- **Logica**: possesso + vicinanza palla + stesso team.
- **Parametri** (sotto `events.pass`):

| Chiave | Default | Descrizione |
|--------|---------|-------------|
| `use_possession` | true | Usa la logica di possesso per identificare il passatore. |
| `max_ball_receiver_distance_m` | 3.0 | Vicinanza massima palla–ricevente per considerare il passaggio completato (stesso team). |
| `same_team_required` | true | Il ricevente deve essere dello stesso team. |

### Recupero

- **Logica**: cambio possesso in **area difensiva** (usare calibrazione per coordinate campo).
- **Parametri** (sotto `events.recovery`):

| Chiave | Default | Descrizione |
|--------|---------|-------------|
| `defensive_area_x_min_m` | 0 | Limite x (metri) area difensiva lato porta sinistra (x minimo). |
| `defensive_area_x_max_m` | 17 | Limite x (metri) area difensiva lato porta sinistra (x massimo). |
| `defensive_area_x_max_other_side_m` | 88 | Limite x area difensiva lato porta destra (x minimo). |
| `defensive_area_x_min_other_side_m` | 105 | Limite x area difensiva lato porta destra (x massimo). |

Su campo FIFA (105×68 m) le due aree difensive sono quindi **x ∈ [0, 17]** e **x ∈ [88, 105]** (circa area di rigore). L’event engine deve convertire le posizioni da pixel a metri con `analysis.homography.get_calibrator()` (o equivalente) prima di confrontare con queste soglie.

### Tiro

- **Logica**: velocità palla + direzione verso porta (usare calibrazione per posizione porte).
- **Parametri** (sotto `events.shot`):

| Chiave | Default | Descrizione |
|--------|---------|-------------|
| `min_ball_speed_m_s` | 5.0 | Velocità minima palla (m/s) per considerare un tiro. |
| `goal_center_y_m` | 34 | Coordinata y (metri) del centro porta (campo FIFA 68 m di larghezza). |
| `goal_left_x_m` | 0 | Coordinata x della porta sinistra. |
| `goal_right_x_m` | 105 | Coordinata x della porta destra. |
| `max_angle_deg_from_goal` | 45 | Angolo massimo (gradi) tra direzione del movimento palla e la linea verso la porta per considerare “verso porta”. |

### Pressing

- **Logica**: raggio attorno alla palla, conteggio giocatori per team.
- **Parametri** (sotto `events.pressing`):

| Chiave | Default | Descrizione |
|--------|---------|-------------|
| `radius_around_ball_m` | 5.0 | Raggio (metri) entro cui contare i giocatori. |
| `min_players_to_count_pressing` | 1 | Numero minimo di giocatori (per team) per considerare un frame di pressing. |

---

## Campo (riferimento)

Sotto `field` sono definite le dimensioni standard FIFA, usate per interpretare le coordinate in metri (e coerenti con la calibrazione):

- `length_m`: 105  
- `width_m`: 68  

---

## Modulo condiviso

- **Modulo**: `analysis.event_engine_params`.
- **Funzioni**:
  - `get_params(config_path=None)` → dict completo (con cache).
  - `get_possession_params(config_path=None)` → solo `possession`.
  - `get_event_params(event_name, config_path=None)` → solo `events[event_name]` (es. `"pass"`, `"recovery"`, `"shot"`, `"pressing"`).
  - `get_field_params(config_path=None)` → solo `field`.
  - `load_params(config_path=None)` → come `get_params` ma senza dipendere dalla cache (utile dopo scrittura file).
  - `clear_cache()` → invalida la cache dopo modifica del file.

Il **backend cloud** può usare lo stesso file `config/event_engine_params.json` (incluso nel repo o copiato nel container) e lo stesso modulo (o una copia) per garantire soglie identiche tra locale e cloud.

---

## Riepilogo

| Componente | Ruolo |
|------------|--------|
| `config/event_engine_params.json` | File unico di soglie (possesso + eventi). Stesso per locale e cloud. |
| `analysis.event_engine_params` | Caricamento, merge con default, API get_params / get_possession_params / get_event_params / get_field_params. |
| Calibrazione | Per recupero e tiro usare `analysis.homography.get_calibrator(calibration_path)` per convertire pixel → metri prima di applicare le soglie. |
