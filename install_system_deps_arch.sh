#!/bin/bash
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Installing System Dependencies for Marin OS (Arch Linux)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

sudo pacman -Syu --noconfirm \
    glib2 \
    mesa \
    tesseract \
    tesseract-data-eng \
    poppler \
    ffmpeg \
    espeak-ng \
    vlc \
    curl \
    ca-certificates \
    supervisor \
    alsa-utils \
    zstd

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ System dependencies installed successfully via pacman!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
