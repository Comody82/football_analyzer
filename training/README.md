# Training modello detection calcio

Dataset: **Roboflow Soccer Players** in `datasets/soccer-yolox-dataset` (formato YOLO: train/valid/test con immagini e label `.txt`).

## Requisiti

```bash
pip install ultralytics
```

(Opzionale: PyYAML non richiesto; i path vengono generati nello script.)

## Training (5 epoche, batch 4)

Dalla **root del progetto** (`c:\football_analyzer`):

```bash
python training/soccer_train.py
```

- Usa **YOLOv8s** (small), 8 classi: Ball, GOAL, Goalie, NED, Ref, USA, football, player.
- Salva i run in `training/runs/soccer/`.
- Copia il miglior checkpoint in **`models/yolov8s_soccer_best.pt`** per uso e fine-tuning.

## Test inference

Dopo il training:

```bash
python training/soccer_test_inference.py
```

Opzionale: indicare un checkpoint diverso e il numero di immagini:

```bash
python training/soccer_test_inference.py --model models/yolov8s_soccer_best.pt --max-images 10 --conf 0.3
```

Le immagini con i box disegnati vengono salvate in **`training/test_output/`**.

## Note

- Per un training completo con **YOLOX-Small** (stesso spirito “small”) bisogna usare il [repo ufficiale YOLOX](https://github.com/Megvii-BaseDetection/YOLOX): creare un’Exp con `num_classes=8`, un Dataset che legga il formato YOLO (o convertire in COCO) e lanciare `tools/train.py`. Qui si usa **YOLOv8s** per compatibilità diretta con il `data.yaml` e per avere subito un modello utilizzabile e fine-tunabile.
