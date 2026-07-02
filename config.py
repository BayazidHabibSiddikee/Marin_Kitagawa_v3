#!/usr/bin/env python3
# config.py — Marin /  HS-02 shared constants  (Linux-native)

import os
import shutil
import subprocess
import json
import random
from typing import Dict, List, Optional
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── APP LAUNCHER ───────────────────────────────────────────────────────────────
APPS: dict[str, list[str]] = {
    "chrome":           ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"],
    "brave":            ["brave-browser", "brave"],
    "firefox":          ["firefox", "firefox-esr"],
    "vscode":           ["code"],
    "terminal":         ["ghostty", "konsole", "xterm", "alacritty", "kitty", "tilix"],
    "file manager":     ["nautilus", "dolphin", "thunar", "nemo", "pcmanfm"],
    "vlc":              ["vlc"],
    "mpv":              ["mpv"],
    "discord":          ["discord", "Discord"],
    "telegram":         ["telegram-desktop", "Telegram"],
    "whatsapp":         ["whatsapp-for-linux"],
}

WEB_APPS: dict[str, str] = {
    "claude":           "https://claude.ai",
    "chatgpt":          "https://chat.openai.com",
    "gemini":           "https://gemini.google.com",
    "youtube":          "https://www.youtube.com",
    "github":           "https://github.com",
}

def launch_app(name: str) -> str:
    key = name.lower().strip()
    if key in APPS:
        for cmd in APPS[key]:
            if shutil.which(cmd):
                try:
                    subprocess.Popen([cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                    return f"Opening {name}~ ✨"
                except: pass
    if key in WEB_APPS:
        import webbrowser
        webbrowser.open(WEB_APPS[key])
        return f"Opening {name} in browser~ 🌐"
    return f"I don't know how to open '{name}' yet."

# ── MODEL CONFIG ───────────────────────────────────────────────────────────────

LOCAL_MODELS = [
    "qwen2.5:1.5b", "marin:latest", "qwen2.5:0.5b", "tinyllama:latest",
]

IMAGE_MODELS = {
    "primary": "sourceful/riverflow-v2.5-pro:free",
    "fallback": "moondream"
}

TASK_ROUTING = {
    "smart_tasks": ["greeting", "status_check", "time_query", "mood", "idle_chat", "hi", "hello",
                    "how are", "what time", "good morning", "good night", "thanks", "thank you",
                    "ok", "okay", "yes", "no", "bye", "what's up", "whats up"],
    "standard_tasks": ["analysis", "summarize", "translate", "explain", "write", "learn", "search"],
    "coding_tasks": ["code", "debug", "review", "refactor", "test", "python"],
    "complex_tasks": ["agent_control", "complex_reasoning", "research", "planning", "autonomous"]
}

# ── SETTINGS LOADER ────────────────────────────────────────────────────────────
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")

def load_settings():
    if not os.path.exists(SETTINGS_PATH): return {}
    try:
        with open(SETTINGS_PATH, "r") as f: return json.load(f)
    except: return {}

_settings = load_settings()

# ── VAULT & API KEYS ─────────────────────────────────────────────────────────
try:
    from vault import vault_get, get_vault
    _v = get_vault()
    _v.migrate_from_settings(SETTINGS_PATH)
    API_KEYS = {}
    for p in ["openai", "gemini", "anthropic", "deepseek"]:
        k = vault_get(f"{p}_api_key")
        if k: API_KEYS[p] = {"api_key": k}
except:
    API_KEYS = _settings.get("api_keys", {})

# ── DYNAMIC DEFAULTS ─────────────────────────────────────────────────────────
# Classifiers use FAST_MODEL (mini model for quick classification)
# LLM replies use DEFAULT_MODEL (large model for quality responses)
FAST_MODEL      = _settings.get("models", {}).get("fast", "qwen2.5:1.5b")
DEFAULT_MODEL   = _settings.get("models", {}).get("default", "google/gemma-2-9b-it:free")
STRATEGY_MODEL  = FAST_MODEL  # Strategist uses fast model for tool planning

# PERSONA: Use the large default model for character responses
PERSONA_MODEL   = DEFAULT_MODEL

VISION_MODEL    = _settings.get("models", {}).get("vision", IMAGE_MODELS["fallback"])
EMBEDDING_MODEL = _settings.get("models", {}).get("embedding", "all-MiniLM-L6-v2")

MODEL_TIERS = {
    "smart_tasks":    [DEFAULT_MODEL],
    "standard_tasks": [DEFAULT_MODEL],
    "complex_tasks":  [DEFAULT_MODEL],
    "coding_tasks":   [DEFAULT_MODEL],
}

# ── SESSION SECRET ───────────────────────────────────────────────────────────
_s_key_path = os.path.join(BASE_DIR, "storage", ".session_key")
def _get_session_key():
    k = os.getenv("SESSION_SECRET_KEY")
    if k: return k
    if os.path.exists(_s_key_path):
        try:
            with open(_s_key_path, "r") as f: return f.read().strip()
        except: pass
    import secrets
    k = secrets.token_hex(32)
    os.makedirs(os.path.dirname(_s_key_path), exist_ok=True)
    try:
        with open(_s_key_path, "w") as f: f.write(k)
    except: pass
    return k

SESSION_SECRET_KEY = _get_session_key()

# ── FAISS INDEX ────────────────────────────────────────────────────────────────
FAISS_DIR = os.path.join(BASE_DIR, "storage", "faiss_index")

# ── EXPORTS ──────────────────────────────────────────────────────────────────
HOST = _settings.get("server", {}).get("host", "0.0.0.0")
PORT = _settings.get("server", {}).get("port", 5069)
RAG_PORT = _settings.get("server", {}).get("rag_port", 5080)
# Use localhost:11434 as default for Ollama
_env_ollama = os.getenv("OLLAMA_BASE_URL")
_set_ollama = _settings.get("server", {}).get("ollama_base_url")
OLLAMA_BASE_URL = _env_ollama or _set_ollama or "http://localhost:11434"

# Use localhost by default since we use network_mode: host
_PROXY_HOST = os.getenv("MARIN_PROXY_HOST", "localhost")

print(f"[Config] OLLAMA_BASE_URL: {OLLAMA_BASE_URL}")

UPLOAD_FOLDER = "static/uploads"

def get_api_key(p): return API_KEYS.get(p, {}).get("api_key")

def classify_task(text: str) -> str:
    text = text.lower()
    for tier, keywords in TASK_ROUTING.items():
        if any(k in text for k in keywords): return tier
    return "standard_tasks"

def get_model_for_task(task_type: str) -> str:
    models = MODEL_TIERS.get(task_type, [])
    if not models: return DEFAULT_MODEL
    return random.choice(models)

# ── MISC ─────────────────────────────────────────────────────────────────────
POMODORO_WORK_MINUTES = 25
MEMORY_MAX_MESSAGES = 50
EMAIL_SENDER = _settings.get("email", {}).get("sender", os.getenv("EMAIL_SENDER", ""))
EMAILS = {}
