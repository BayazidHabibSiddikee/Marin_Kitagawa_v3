FROM python:3.11-slim AS base

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System dependencies for:
# - opencv-python: libgl1, libglib2.0-0
# - pytesseract: tesseract-ocr
# - pdf2image: poppler-utils
# - pydub/audio: ffmpeg
# - espeak (pyttsx3 fallback): espeak
# - general: curl, git, build-essential
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    poppler-utils \
    ffmpeg \
    espeak \
    vlc-bin \
    libvlc-dev \
    curl \
    ca-certificates \
    supervisor \
    alsa-utils \
    zstd \
    && rm -rf /var/lib/apt/lists/*

# NOTE: Ollama runs on the HOST machine, not inside this container.
# The container connects to it via OLLAMA_BASE_URL=http://host.docker.internal:11434

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --default-timeout=1000 -r requirements.txt

# Copy project
COPY . .

# Create all necessary directories
RUN mkdir -p \
    storage \
    logs \
    static/uploads \
    static/generated \
    static/downloads \
    doc \
    code \
    unique/marin_vault \
    storage/faiss_db \
    /root/.piper-voices

# Pre-download Piper voice models
RUN curl -sSL https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx -o /root/.piper-voices/en_US-amy-medium.onnx && \
    curl -sSL https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx.json -o /root/.piper-voices/en_US-amy-medium.onnx.json

# Make scripts executable
RUN chmod +x docker-entrypoint.sh 2>/dev/null || true

# Expose all service ports
# 5069 = Main chat UI
# 5080 = RAG server
# 5070 = ModuleFlow (optional)
EXPOSE 5069 5080 5070

ENTRYPOINT ["./docker-entrypoint.sh"]
