# Fase 2 – Dataset in formato COCO per YOLOX (completata)

## Scelta: Opzione A (conversione YOLO → COCO)

## Fatto

### 1. Script di conversione
- **File:** `training/yolo_to_coco_soccer.py`
- Legge il dataset Roboflow in `datasets/soccer-yolox-dataset` (train/images, train/labels, valid/images, valid/labels).
- Converte le label YOLO (classe, x_center, y_center, w, h normalizzati) in annotazioni COCO (bbox in pixel).
- Scrive:
  - `YOLOX/datasets/soccer/annotations/instances_train2017.json`
  - `YOLOX/datasets/soccer/annotations/instances_val2017.json`
- Copia le immagini in:
  - `YOLOX/datasets/soccer/train2017/`
  - `YOLOX/datasets/soccer/val2017/`

**Esecuzione (dalla root football_analyzer):**
```bash
python training/yolo_to_coco_soccer.py
```
Opzionale: `--source path/to/yolo_dataset --output path/to/YOLOX/datasets/soccer`

### 2. Dataset collocato
- **Percorso:** `c:\YOLOX\datasets\soccer\`
- Struttura:
  - `annotations/instances_train2017.json` (243 immagini, 3449 annotazioni)
  - `annotations/instances_val2017.json` (68 immagini, 980 annotazioni)
  - `train2017/*.jpg`
  - `val2017/*.jpg`
- **8 classi:** Ball, GOAL, Goalie, NED, Ref, USA, football, player (category_id 1–8 in COCO).

### 3. Exp YOLOX per soccer
- **File:** `c:\YOLOX\exps\example\yolox_soccer\yolox_soccer_s.py`
- `data_dir = "datasets/soccer"`, `num_classes = 8`, stesso `train_ann` / `val_ann` COCO standard.

## Training (quando hai GPU)

Da `c:\YOLOX`:
```bash
python -m yolox.tools.train -f exps/example/yolox_soccer/yolox_soccer_s.py -d 1 -b 4 -c path/to/yolox_s.pth
```
- `-c yolox_s.pth`: checkpoint pre-trained COCO (opzionale ma consigliato).
- Per una prova breve: aggiungi `max_epoch 5` in coda al comando.

## Aggiornare il dataset

Se riesporti da Roboflow o aggiungi immagini/label:
1. Aggiorna `datasets/soccer-yolox-dataset` (train/valid).
2. Rilancia: `python training/yolo_to_coco_soccer.py` (sovrascrive JSON e copia le immagini in YOLOX/datasets/soccer).

## Prossimo passo (Fase 3)

Configurare e lanciare il training (Fase 4 nel piano originale: training, salvataggio checkpoint, poi integrazione nell’app).
