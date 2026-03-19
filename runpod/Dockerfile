# ─── Base: Python 3.11 slim (PyTorch installato via pip con CUDA 12.1) ─────────
FROM python:3.11-slim

WORKDIR /app

# Dipendenze di sistema per OpenCV e git
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgl1-mesa-glx \
    libglib2.0-0 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# PyTorch 2.4.0 con CUDA 12.1 (via pip ufficiale)
RUN pip install --no-cache-dir \
    torch==2.4.0 torchvision==0.19.0 \
    --index-url https://download.pytorch.org/whl/cu121

# Altre dipendenze
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

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

CMD ["python", "-u", "handler.py"]
