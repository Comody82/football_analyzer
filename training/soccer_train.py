"""
Training modello detection sul dataset calcio (Roboflow).
Usa YOLOv8s (small) con data.yaml in formato YOLO.
Batch size 4, 5 epoche; checkpoint salvato per eventuale fine-tuning.

Esegui dalla root del progetto:
  python training/soccer_train.py

Richiede: pip install ultralytics
"""
from pathlib import Path
import sys

# Root progetto = parent della cartella training
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = PROJECT_ROOT / "datasets" / "soccer-yolox-dataset"
DATA_YAML = DATASET_DIR / "data.yaml"
RUNS_DIR = PROJECT_ROOT / "training" / "runs"
MODELS_DIR = PROJECT_ROOT / "models"

# Parametri richiesti
BATCH_SIZE = 4
EPOCHS = 5
MODEL_SIZE = "s"  # YOLOv8s = small (analogo a YOLOX-Small)


def _make_data_yaml_with_absolute_paths() -> Path:
    """Crea un data.yaml con path assoluti per Ultralytics."""
    out = PROJECT_ROOT / "training" / "data_soccer_abs.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    base = str(DATASET_DIR.resolve()).replace("\\", "/")
    content = f"""# Generated for training - absolute paths
path: {base}
train: train/images
val: valid/images
test: test/images

nc: 8
names: ['Ball', 'GOAL', 'Goalie', 'NED', 'Ref', 'USA', 'football', 'player']
"""
    out.write_text(content, encoding="utf-8")
    return out


def main():
    if not DATASET_DIR.exists():
        print(f"Dataset non trovato: {DATASET_DIR}")
        sys.exit(1)
    if not (DATASET_DIR / "train" / "images").exists():
        print(f"Cartella train/images non trovata in {DATASET_DIR}")
        sys.exit(1)

    try:
        from ultralytics import YOLO
    except ImportError:
        print("Installa ultralytics: pip install ultralytics")
        sys.exit(1)

    # Data yaml con path assoluti
    data_yaml = _make_data_yaml_with_absolute_paths()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    model_name = f"yolov8{MODEL_SIZE}.pt"
    print(f"Modello: {model_name} | Epochs: {EPOCHS} | Batch: {BATCH_SIZE}")
    print(f"Dataset: {DATASET_DIR}")
    print(f"Data yaml: {data_yaml}")

    model = YOLO(model_name)
    results = model.train(
        data=str(data_yaml),
        epochs=EPOCHS,
        batch=BATCH_SIZE,
        project=str(RUNS_DIR),
        name="soccer",
        exist_ok=True,
        pretrained=True,
        verbose=True,
    )

    # Copia il miglior checkpoint in models/ per uso e fine-tuning
    best_pt = Path(results.save_dir) / "weights" / "best.pt"
    if best_pt.exists():
        dest = MODELS_DIR / "yolov8s_soccer_best.pt"
        import shutil
        shutil.copy2(best_pt, dest)
        print(f"Checkpoint salvato: {dest}")
    else:
        print("best.pt non trovato; controlla training/runs/soccer/")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
