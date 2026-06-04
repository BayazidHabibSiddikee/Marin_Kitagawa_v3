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
# - general: curl, git
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    poppler-utils \
    ffmpeg \
    espeak \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy project
COPY . .

# Create necessary directories
RUN mkdir -p storage logs static/uploads static/generated static/downloads

# Make scripts executable
RUN chmod +x docker-entrypoint.sh 2>/dev/null || true

EXPOSE 5069 5080 5070

ENTRYPOINT ["./docker-entrypoint.sh"]
