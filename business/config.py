#!/usr/bin/env python3
# config.py — Pure Business Advisor constants

import os
import json

# ── CONFIG LOADER ──────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")

def load_settings():
    if not os.path.exists(SETTINGS_PATH):
        return {}
    try:
        with open(SETTINGS_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading settings.json: {e}")
        return {}

_settings = load_settings()

# ── MODEL CONFIG ───────────────────────────────────────────────────────────────
DEFAULT_MODEL = _settings.get("models", {}).get("default", "gemma4:31b-cloud")
FAST_MODEL    = _settings.get("models", {}).get("fast", "qwen2.5:0.5b")
VISION_MODEL  = _settings.get("models", {}).get("vision", "leo")
EMBEDDING_MODEL = _settings.get("models", {}).get("embedding", "all-MiniLM-L6-v2")

# ── SESSION CONFIG ─────────────────────────────────────────────────────────────
MEMORY_MAX_MESSAGES    = 50

# ── SERVER ─────────────────────────────────────────────────────────────────────
HOST            = _settings.get("server", {}).get("host", "0.0.0.0")
PORT            = _settings.get("server", {}).get("port", 5069)
OLLAMA_BASE_URL = _settings.get("server", {}).get("ollama_base_url", "http://localhost:11434")
UPLOAD_FOLDER   = os.path.join(BASE_DIR, "static", "uploads")

# Set Ollama host for the python library
os.environ["OLLAMA_HOST"] = OLLAMA_BASE_URL

# ── API KEYS ───────────────────────────────────────────────────────────────────
API_KEYS = _settings.get("api_keys", {})
