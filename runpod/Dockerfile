# ─── Base image: PyTorch 2.4 + CUDA 12.1 (runtime, più leggera) ───────────────
FROM pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime

WORKDIR /app

# Dipendenze di sistema necessarie per OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgl1-mesa-glx \
    libglib2.0-0 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Dipendenze Python
COPY runpod/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Installa YOLOX dalla sorgente ufficiale
RUN git clone https://github.com/Megvii-BaseDetection/YOLOX.git /tmp/yolox \
    && pip install --no-cache-dir -e /tmp/yolox \
    && rm -rf /tmp/yolox/.git

# Copia codice dell'app
COPY analysis/ /app/analysis/
COPY r2_storage.py /app/r2_storage.py
COPY runpod/handler.py /app/handler.py

# Directory modelli (il modello viene scaricato da R2 al primo avvio)
RUN mkdir -p /app/models

# Variabili d'ambiente (sostituite a runtime con i secrets di RunPod)
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

CMD ["python", "-u", "handler.py"]
