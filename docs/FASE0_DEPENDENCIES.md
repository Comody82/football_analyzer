# Fase 0: Verifica dipendenze

> Data verifica: 2025-02-25

---

## 1. requirements.txt

```
PyQt5>=5.15.0
opencv-python>=4.8.0
numpy>=1.24.0
scikit-learn>=1.3.0
torch>=1.10.0
torchvision>=0.11.0
yolox>=0.3.0
```

**Note da requirements.txt:**
- Su Python 3.10 Windows, YOLOX può richiedere installazione a parte (`pip install yolox --no-deps` + dipendenze manuali).
- CMake può essere necessario (winget install Kitware.CMake).

---

## 2. Verifica installate (ambiente attuale)

| Pacchetto | Versione rilevata | Stato |
|-----------|-------------------|--------|
| Python | 3.10.11 | OK |
| PyTorch | 2.10.0+cpu | OK |
| TorchVision | 0.25.0+cpu | OK |
| OpenCV | 4.13.0 | OK |
| NumPy | 2.2.6 | OK |
| YOLOX | OK (import yolox.exp) | OK |
| scipy | OK | OK |
| scikit-learn | OK | OK |
| PyQt5 | OK | OK |

**Nota:** PyTorch è installato in versione CPU. Per l’analysis_engine con GPU occorrerà la build CUDA.

---

## 3. Dipendenze per analysis_engine (future)

Per la CLI `analysis_engine` e l’exe standalone:
- Tutte le dipendenze sopra (PyTorch, YOLOX, OpenCV, numpy, scipy, scikit-learn).
- **psutil** (per limiti CPU e priorità processo) — da aggiungere a requirements.
- **argparse** (stdlib) — già incluso.

---

## 4. Compatibilità Python

- Progetto sviluppato/testato su Python 3.10.
- PyInstaller per `analysis_engine.exe` andrà testato sullo stesso Python 3.10.
