# Fase 1 – Ambiente e repo YOLOX (completata)

## Fatto

1. **Repo clonato** in `c:\YOLOX`  
   - `git clone https://github.com/Megvii-BaseDetection/YOLOX.git`

2. **Dipendenze installate**  
   - Da `c:\YOLOX`: `pip install -v -e .`  
   - Installati: torch, torchvision, pycocotools, loguru, ninja, tabulate, tensorboard, onnx, ecc.  
   - Verifica: `python -c "import yolox; print(yolox.__file__)"` → OK

3. **Dataset di test (coco128)**  
   - Scaricato con gdown da Google Drive (link nella doc YOLOX) in `c:\YOLOX\datasets\coco128.zip`  
   - Estratto in `c:\YOLOX\datasets\coco128\`  
   - Struttura: `annotations/` (instances_train2017.json, instances_val2017.json), `train2017/`, `val2017/` con immagini

4. **Exp custom**  
   - `exps/example/custom/yolox_s.py`: usa `data_dir = "datasets/coco128"`, `num_classes = 80`  
   - Per una prova rapida si può lanciare 1 epoca con:  
     `max_epoch 1` in coda ai comandi sotto

## Verifica training (richiede GPU)

Su questa macchina PyTorch è **solo CPU**, quindi il training va in errore su `torch.cuda.set_device`. Per **verificare che il training parta e completi un’epoca** serve un ambiente con **CUDA** (o usare lo stesso comando in cloud).

Da **`c:\YOLOX`**:

```bash
# 1 GPU, batch 4, 1 epoca (prova)
python -m yolox.tools.train -f exps/example/custom/yolox_s.py -d 1 -b 4 max_epoch 1

# Con checkpoint pre-trained (opzionale, stesso risultato per il test)
python -m yolox.tools.train -f exps/example/custom/yolox_s.py -d 1 -b 4 max_epoch 1 -c path/to/yolox_s.pth
```

- **-d 1**: 1 GPU  
- **-d 0** non abilita la CPU: il trainer si aspetta comunque CUDA.

Output atteso: avvio training, log delle iterazioni, fine epoca 1 e salvataggio in `YOLOX_outputs/`.

## Prossimo passo (Fase 2)

Preparare il **dataset calcio** in formato usabile da YOLOX (conversione YOLO → COCO o Dataset custom che legga le label in formato YOLO). Vedi piano in `training/README.md` e piano step-by-step concordato.
