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
    curl \
    git \
    build-essential \
    sudo \
    procps \
    iproute2 \
    iptables \
    net-tools \
    iputils-ping \
    nmap \
    wget \
    vim \
    nano \
    htop \
    lsof \
    strace \
    tcpdump \
    netcat-openbsd \
    dnsutils \
    cron \
    at \
    && rm -rf /var/lib/apt/lists/*

# Give the app user unrestricted sudo inside the container
RUN echo "root ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install -r requirements.txt

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
    storage/faiss_db

# Make scripts executable
RUN chmod +x docker-entrypoint.sh 2>/dev/null || true

# Expose all service ports
# 5069 = Main chat UI
# 5080 = RAG server
# 5070 = ModuleFlow (optional)
EXPOSE 5069 5080 5070

ENTRYPOINT ["./docker-entrypoint.sh"]
