#!/usr/bin/env python3
# config.py — Marin /  HS-02 shared constants  (Linux-native)

import os
import shutil
import subprocess

# ── APP LAUNCHER ───────────────────────────────────────────────────────────────
# Each entry is a list of candidate commands tried left-to-right.
# The first one found on PATH (via shutil.which) is used.
# Use 'xdg-open <path>' for file-manager / default-app fallbacks.
APPS: dict[str, list[str]] = {
    # Browsers
    "chrome":           ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"],
    "brave":            ["brave-browser", "brave"],
    "firefox":          ["firefox", "firefox-esr"],
    "edge":             ["microsoft-edge", "microsoft-edge-stable"],
    "opera":            ["opera"],

    # Editors / IDEs
    "vscode":           ["code"],
    "vs code":          ["code"],
    "nvim":             ["nvim"],
    "neovim":           ["nvim"],
    "vim":              ["vim"],
    "nano":             ["nano"],
    "gedit":            ["gedit"],
    "kate":             ["kate"],
    "sublime":          ["subl", "sublime_text"],
    "atom":             ["atom"],

    # Terminals
    "terminal":         ["ghostty", "konsole", "xterm", "alacritty", "kitty", "tilix"],
    "konsole":          ["konsole"],
    "alacritty":        ["alacritty"],
    "kitty":            ["kitty"],

    # File managers
    "file manager":     ["nautilus", "dolphin", "thunar", "nemo", "pcmanfm"],
    "files":            ["nautilus", "dolphin", "thunar", "nemo"],

    # System tools
    "task manager":     ["gnome-system-monitor", "ksysguard", "htop", "btop"],
    "calculator":       ["gnome-calculator", "kcalc", "galculator", "qalculate-gtk"],
    "text editor":      ["gedit", "kate", "mousepad", "xed"],
    "settings":         ["gnome-control-center", "systemsettings5", "xfce4-settings-manager"],
    "screenshot":       ["gnome-screenshot", "spectacle", "flameshot"],

    # Multimedia
    "vlc":              ["vlc"],
    "mpv":              ["mpv"],
    "rhythmbox":        ["rhythmbox"],
    "spotify":          ["spotify"],
    "obs":              ["obs"],
    "audacity":         ["audacity"],
    "gimp":             ["gimp"],
    "inkscape":         ["inkscape"],

    # Office
    "libreoffice":      ["libreoffice"],
    "writer":           ["libreoffice", "--writer"],   # handled specially below
    "calc":             ["libreoffice", "--calc"],
    "impress":          ["libreoffice", "--impress"],

    # Dev tools
    "postman":          ["postman"],
    "dbeaver":          ["dbeaver"],
    "docker":           ["docker"],
    "virtualbox":       ["virtualbox"],

    # Communication
    "discord":          ["discord", "Discord"],
    "telegram":         ["telegram-desktop", "Telegram"],
    "slack":            ["slack"],
    "zoom":             ["zoom"],
    "teams":            ["teams", "teams-for-linux"],
    "whatsapp":         ["whatsapp-for-linux"],
}

WEB_APPS: dict[str, str] = {
    "claude":           "https://claude.ai",
    "chatgpt":          "https://chat.openai.com",
    "gemini":           "https://gemini.google.com",
    "youtube":          "https://www.youtube.com",
    "github":           "https://github.com",
    "stackoverflow":    "https://stackoverflow.com",
    "google":           "https://www.google.com",
    "gmail":            "https://mail.google.com",
    "drive":            "https://drive.google.com",
    "notion":           "https://www.notion.so",
    "telegram":         "https://web.telegram.org/k/",
    "discord":          "https://discord.com/app",
    "reddit":           "https://www.reddit.com",
    "twitter":          "https://twitter.com",
    "linkedin":         "https://www.linkedin.com",
    "leetcode":         "https://leetcode.com",
    "colab":            "https://colab.research.google.com",
    "kaggle":           "https://www.kaggle.com",
}


def _find_cmd(candidates: list[str]) -> list[str] | None:
    """Return the first usable command from candidates as a list ready for Popen."""
    # Handle multi-token entries like ["libreoffice", "--writer"]
    if len(candidates) >= 2 and candidates[0].startswith("libreoffice"):
        if shutil.which("libreoffice"):
            return candidates   # return as-is, e.g. ["libreoffice", "--writer"]
        return None
    for cmd in candidates:
        if shutil.which(cmd):
            return [cmd]
    return None


def launch_app(name: str) -> str:
    """
    Launch a desktop app or open a web app in the default browser.
    Returns a human-readable status string (for Marin to speak).
    """
    key = name.lower().strip()

    # 1. Try desktop APPS dict
    if key in APPS:
        cmd = _find_cmd(APPS[key])
        if cmd:
            try:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,     # detach fully from parent
                )
                return f"Opening {name}~ ✨"
            except Exception as e:
                return f"Found {name} but couldn't launch it: {e}"
        else:
            # App listed but not installed — fall through to web fallback
            if key in WEB_APPS:
                return _open_url(WEB_APPS[key], name)
            return (
                f"I couldn't find {name} installed on your system. "
                f"Try: sudo apt install {APPS[key][0]}"
            )

    # 2. Try WEB_APPS dict
    if key in WEB_APPS:
        return _open_url(WEB_APPS[key], name)

    # 3. Last resort: try xdg-open with the raw name (might work for .desktop files)
    if shutil.which(key):
        try:
            subprocess.Popen(
                [key],
                stdout=open('/home/sword/Documents/xMarin/logs/tool_execution.log', 'a'),
                stderr=open('/home/sword/Documents/xMarin/logs/tool_execution.log', 'a'),
                start_new_session=True,
            )
            return f"Opening {name}~ ✨"
        except Exception as e:
            return f"Tried to open {name} but got: {e}"

    return f"I don't know how to open '{name}' yet. Add it to config.py!"


def _open_url(url: str, label: str) -> str:
    """Open a URL with xdg-open (Linux default browser)."""
    try:
        subprocess.Popen(
            ["xdg-open", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return f"Opening {label} in your browser~ 🌐"
    except FileNotFoundError:
        # xdg-open not found — try python's webbrowser as last resort
        import webbrowser
        webbrowser.open(url)
        return f"Opening {label}~ 🌐"
    except Exception as e:
        return f"Couldn't open {label}: {e}"


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