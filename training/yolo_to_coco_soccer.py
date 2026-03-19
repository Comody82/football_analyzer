"""
Converte il dataset calcio (formato YOLO / Roboflow) in formato COCO
per il training YOLOX. Genera instances_train2017.json e instances_val2017.json
e copia le immagini in YOLOX/datasets/soccer/train2017 e val2017.

Esegui dalla root del progetto (football_analyzer):
  python training/yolo_to_coco_soccer.py

Oppure con path espliciti:
  python training/yolo_to_coco_soccer.py --source datasets/soccer-yolox-dataset --output c:/YOLOX/datasets/soccer
"""
from pathlib import Path
import argparse
import json
import shutil

# Default paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = PROJECT_ROOT / "datasets" / "soccer-yolox-dataset"
DEFAULT_OUTPUT = PROJECT_ROOT.parent / "YOLOX" / "datasets" / "soccer"

# 8 classi come in data.yaml (ordine Roboflow). NED/USA rinominati in team A / team B.
CLASS_NAMES = ["Ball", "GOAL", "Goalie", "team A", "Ref", "team B", "football", "player"]


def get_image_size(img_path: Path):
    import cv2
    im = cv2.imread(str(img_path))
    if im is None:
        return None, None
    h, w = im.shape[:2]
    return w, h


def yolo_line_to_coco_bbox(line: str, img_w: int, img_h: int):
    """YOLO: class_id x_center y_center width height (normalized). -> COCO: [x_min, y_min, w, h] pixels."""
    parts = line.strip().split()
    if len(parts) < 5:
        return None
    try:
        cls_id = int(parts[0])
        xc = float(parts[1])
        yc = float(parts[2])
        w_n = float(parts[3])
        h_n = float(parts[4])
    except ValueError:
        return None
    x_min = (xc - w_n / 2) * img_w
    y_min = (yc - h_n / 2) * img_h
    w_px = w_n * img_w
    h_px = h_n * img_h
    # clip to image
    x_min = max(0, min(img_w - 1, x_min))
    y_min = max(0, min(img_h - 1, y_min))
    w_px = max(0, min(img_w - x_min, w_px))
    h_px = max(0, min(img_h - y_min, h_px))
    if w_px <= 0 or h_px <= 0:
        return None
    return {
        "category_id": cls_id + 1,  # COCO 1-indexed
        "bbox": [round(x_min, 2), round(y_min, 2), round(w_px, 2), round(h_px, 2)],
        "area": round(w_px * h_px, 2),
        "iscrowd": 0,
    }


def process_split(source_dir: Path, split: str, out_dir: Path, images_out: Path):
    """split in ('train', 'valid')."""
    img_dir = source_dir / split / "images"
    lbl_dir = source_dir / split / "labels"
    if not img_dir.exists():
        return None, None
    img_exts = (".jpg", ".jpeg", ".png")
    images_list = []
    annotations_list = []
    image_id = 1
    ann_id = 1
    images_out.mkdir(parents=True, exist_ok=True)
    for img_path in sorted(img_dir.iterdir()):
        if img_path.suffix.lower() not in img_exts:
            continue
        stem = img_path.stem
        lbl_path = lbl_dir / f"{stem}.txt"
        w, h = get_image_size(img_path)
        if w is None:
            continue
        file_name = img_path.name
        images_list.append({
            "id": image_id,
            "file_name": file_name,
            "width": w,
            "height": h,
        })
        if lbl_path.exists():
            with open(lbl_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    ann = yolo_line_to_coco_bbox(line, w, h)
                    if ann is None:
                        continue
                    ann["id"] = ann_id
                    ann["image_id"] = image_id
                    annotations_list.append(ann)
                    ann_id += 1
        image_id += 1
        dest = images_out / file_name
        if not dest.exists() or dest.stat().st_size != img_path.stat().st_size:
            shutil.copy2(img_path, dest)
    return images_list, annotations_list


def build_coco_json(images: list, annotations: list, categories: list):
    return {
        "info": {"description": "Soccer dataset (YOLO->COCO)", "version": "1.0"},
        "licenses": [],
        "images": images,
        "annotations": annotations,
        "categories": categories,
    }


def main():
    parser = argparse.ArgumentParser(description="YOLO (Roboflow) -> COCO for YOLOX soccer")
    parser.add_argument("--source", type=str, default=str(DEFAULT_SOURCE), help="Root del dataset YOLO (train/valid/images e labels)")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="Root output (YOLOX/datasets/soccer)")
    args = parser.parse_args()
    source_dir = Path(args.source)
    out_dir = Path(args.output)
    if not source_dir.exists():
        print(f"Source non trovato: {source_dir}")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    ann_dir = out_dir / "annotations"
    ann_dir.mkdir(parents=True, exist_ok=True)
    categories = [{"id": i + 1, "name": n} for i, n in enumerate(CLASS_NAMES)]

    # Train
    train2017 = out_dir / "train2017"
    train_images, train_anns = process_split(source_dir, "train", out_dir, train2017)
    if not train_images:
        print("Nessuna immagine train trovata.")
        return 1
    train_json = build_coco_json(train_images, train_anns, categories)
    with open(ann_dir / "instances_train2017.json", "w", encoding="utf-8") as f:
        json.dump(train_json, f, indent=2)
    print(f"Train: {len(train_images)} immagini, {len(train_anns)} annotazioni -> {ann_dir / 'instances_train2017.json'}")

    # Val
    val2017 = out_dir / "val2017"
    val_images, val_anns = process_split(source_dir, "valid", out_dir, val2017)
    if not val_images:
        print("Nessuna immagine valid trovata.")
    else:
        val_json = build_coco_json(val_images, val_anns, categories)
        with open(ann_dir / "instances_val2017.json", "w", encoding="utf-8") as f:
            json.dump(val_json, f, indent=2)
        print(f"Val:   {len(val_images)} immagini, {len(val_anns)} annotazioni -> {ann_dir / 'instances_val2017.json'}")

    print(f"Dataset COCO pronto in: {out_dir}")
    return 0


if __name__ == "__main__":
    exit(main())
