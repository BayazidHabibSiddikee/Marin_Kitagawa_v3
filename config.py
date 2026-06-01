#!/usr/bin/env python3
# config.py — Marin HS-02 shared constants

import os
import json

# ── CONFIG LOADER ──────────────────────────────────────────────────────────────
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

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
POMODORO_WORK_MINUTES  = 25
POMODORO_BREAK_MINUTES = 5
POMODORO_LONG_BREAK    = 15
MEMORY_MAX_MESSAGES    = 50

# ── SERVER ─────────────────────────────────────────────────────────────────────
HOST            = _settings.get("server", {}).get("host", "0.0.0.0")
PORT            = _settings.get("server", {}).get("port", 5069)
RAG_PORT        = _settings.get("server", {}).get("rag_port", 5080)
MODULEFLOW_PORT = 5070
TODO_PORT       = 5000
OLLAMA_BASE_URL = _settings.get("server", {}).get("ollama_base_url", "http://localhost:11434")
OPENAI_BASE_URL = _settings.get("server", {}).get("openai_base_url", "https://api.openai.com/v1")
UPLOAD_FOLDER   = "static/uploads"

# Set Ollama host for the python library
os.environ["OLLAMA_HOST"] = OLLAMA_BASE_URL

# ── API KEYS ───────────────────────────────────────────────────────────────────
API_KEYS = _settings.get("api_keys", {})

# ── EMAIL ──────────────────────────────────────────────────────────────────────
EMAIL_SENDER = _settings.get("email", {}).get("sender", os.getenv("EMAIL_SENDER", ""))
EMAILS: dict[str, str] = {
    # "name": "email@example.com"
    # Add your contacts here
}