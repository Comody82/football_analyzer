# Fase 3: Build eseguibile analysis_engine

> 2025-02-25

---

## Prerequisiti

- Python 3.10
- Tutte le dipendenze del progetto (`pip install -r requirements.txt`)
- PyInstaller: `pip install pyinstaller`

---

## Build

```bash
cd c:\football_analyzer
pyinstaller build_engine.spec --noconfirm
```

**Tempo atteso:** 5–15 minuti (PyTorch + YOLOX = build pesante).

---

## Output

- **`dist/analysis_engine/`** – cartella con:
  - `analysis_engine.exe` – eseguibile principale
  - DLL e moduli Python (torch, cv2, ecc.)
  - `models/` – creata a runtime; i pesi YOLOX vanno qui o vengono scaricati al primo avvio

---

## Modelli YOLOX

Al primo avvio l'exe tenta di scaricare `yolox_s.pth` nella cartella `models/` **accanto all'exe**.

- **Posizionamento:** la cartella `models` viene creata nella stessa directory dell’exe.
- **Pre-download:** puoi scaricare manualmente e copiare `yolox_s.pth` in `dist/analysis_engine/models/` prima di usare l’exe.

---

## Test

```bash
cd dist\analysis_engine
.\analysis_engine.exe --help
.\analysis_engine.exe --video path\to\video.mp4 --output path\to\project_dir --mode full --no-priority
```

`--no-priority` serve per il test rapido senza modificare la priorità del processo.

---

## Path quando frozen

`get_models_dir()` in `analysis/player_detection.py` usa la directory dell’eseguibile quando l’app gira da exe:

- **Normale:** `Path(__file__).parent.parent / "models"`
- **Frozen (exe):** `Path(sys.executable).parent / "models"`

---

## Modifica al codice

- `analysis/player_detection.py`: `get_models_dir()` adattato per `sys.frozen` (exe).
- `build_engine.spec`: spec PyInstaller con modalità onedir per compatibilità con PyTorch.
