FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    TESSERACT_CMD=/usr/bin/tesseract \
    HOST=0.0.0.0 \
    PORT=7860 \
    INSIGHTFACE_DET_SIZE=320

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd \
    libgl1 libglib2.0-0 libgomp1 curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces runs as uid 1000. Create it and own everything.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface

WORKDIR /home/user/app

COPY --chown=user backend/requirements.txt ./requirements.txt

# CPU-only torch. Saves ~2 GB of CUDA libraries you cannot use.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      -r requirements.txt

# Bake model weights into the image so cold requests are instant.
RUN python -c "\
from insightface.app import FaceAnalysis; \
a = FaceAnalysis(name='buffalo_l', allowed_modules=['detection','recognition'], providers=['CPUExecutionProvider']); \
a.prepare(ctx_id=0, det_size=(320,320))"

RUN python -c "\
from transformers import pipeline; \
pipeline('image-classification', model='prithivMLmods/deepfake-detector-model-v1', device=-1)"

COPY --chown=user backend ./

EXPOSE 7860
CMD ["python", "server.py"]
