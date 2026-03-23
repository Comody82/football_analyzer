"""
Test inference del modello addestrato su immagini di test.
Disegna i box su alcune immagini e salva in training/test_output/.

Esegui dalla root del progetto dopo il training:
  python training/soccer_test_inference.py

Opzionale: python training/soccer_test_inference.py --model models/yolov8s_soccer_best.pt
"""
import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = PROJECT_ROOT / "datasets" / "soccer-yolox-dataset"
DEFAULT_MODEL = PROJECT_ROOT / "models" / "yolov8s_soccer_best.pt"
RUNS_BEST = PROJECT_ROOT / "training" / "runs" / "soccer" / "weights" / "best.pt"
TEST_OUT_DIR = PROJECT_ROOT / "training" / "test_output"


def main():
    parser = argparse.ArgumentParser(description="Test inference modello soccer")
    parser.add_argument("--model", type=str, default=None, help="Path a best.pt o yolov8s_soccer_best.pt")
    parser.add_argument("--max-images", type=int, default=6, help="Numero massimo di immagini da elaborare")
    parser.add_argument("--conf", type=float, default=0.25, help="Soglia confidence")
    args = parser.parse_args()

    model_path = args.model
    if not model_path:
        if DEFAULT_MODEL.exists():
            model_path = str(DEFAULT_MODEL)
        elif RUNS_BEST.exists():
            model_path = str(RUNS_BEST)
        else:
            print("Nessun checkpoint trovato. Esegui prima: python training/soccer_train.py")
            sys.exit(1)
    model_path = Path(model_path)
    if not model_path.exists():
        print(f"Modello non trovato: {model_path}")
        sys.exit(1)

    test_images = DATASET_DIR / "test" / "images"
    if not test_images.exists():
        # Fallback: valid/images
        test_images = DATASET_DIR / "valid" / "images"
    if not test_images.exists():
        test_images = DATASET_DIR / "train" / "images"
    if not test_images.exists():
        print(f"Nessuna cartella immagini trovata in {DATASET_DIR}")
        sys.exit(1)

    try:
        from ultralytics import YOLO
    except ImportError:
        print("Installa ultralytics: pip install ultralytics")
        sys.exit(1)

    images = list(test_images.glob("*.jpg")) + list(test_images.glob("*.png"))
    images = images[: args.max_images]
    if not images:
        print(f"Nessuna immagine in {test_images}")
        sys.exit(1)

    TEST_OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Modello: {model_path} | Immagini: {len(images)} | Output: {TEST_OUT_DIR}")

    import cv2
    model = YOLO(str(model_path))
    for i, img_path in enumerate(images):
        results = model.predict(source=str(img_path), conf=args.conf, save=False, verbose=False)
        if not results:
            continue
        r = results[0]
        out_name = f"out_{i}_{img_path.stem}.jpg"
        out_path = TEST_OUT_DIR / out_name
        img_with_boxes = r.plot()
        cv2.imwrite(str(out_path), img_with_boxes)
        n = len(r.boxes) if r.boxes is not None else 0
        print(f"  Salvato: {out_path.name} (box: {n})")

    print("Fatto. Controlla le immagini in", TEST_OUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
