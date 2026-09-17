FROM python:3.11-slim

# Google Cloud Run Optimized Production Container
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    TESSERACT_CMD=/usr/bin/tesseract \
    HOST=0.0.0.0 \
    PORT=8080 \
    INSIGHTFACE_DET_SIZE=320

# Install system dependencies required for OCR, OpenCV, and ONNX Runtime
# build-essential is installed to compile insightface Cython extensions, then purged to reduce image size
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng \
    libgl1 libglib2.0-0 libgomp1 curl build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt

# Install CPU-only PyTorch wheel and backend requirements, then strip build compilers
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      -r requirements.txt && \
    apt-get purge -y --auto-remove build-essential && \
    rm -rf /var/lib/apt/lists/*

# Bake model weights into container image during build to eliminate runtime download delay
RUN python -c "\
from insightface.app import FaceAnalysis; \
a = FaceAnalysis(name='buffalo_l', allowed_modules=['detection','recognition'], providers=['CPUExecutionProvider']); \
a.prepare(ctx_id=0, det_size=(320,320))"

RUN python -c "\
from transformers import pipeline; \
pipeline('image-classification', model='prithivMLmods/deepfake-detector-model-v1', device=-1)"

COPY backend ./

# Google Cloud Run dynamically injects $PORT (default 8080)
EXPOSE 8080

CMD ["python", "server.py"]
