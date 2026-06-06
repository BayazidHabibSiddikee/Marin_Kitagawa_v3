#!/usr/bin/env python3
# config.py — Marin HS-02 Enhanced Configuration with Model Routing & Docker Control

import os
import shutil
import subprocess
import json
from dotenv import load_dotenv
from typing import Dict, List, Optional
load_dotenv()

# ═══════════════════════════════════════════════════════════════════════════════
# MODEL ROUTING & TIER CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Local models (Ollama) - ONLY these two for fast/smart chat
LOCAL_MODELS = [
    "qwen2.5:0.5b",
    "tinyllama"
]

# Cloud Free Models (OpenRouter)
# DEFAULT: cognitivecomputations/dolphin-mistral-24b-venice-edition:free (Uncensored)
CLOUD_FREE_MODELS = {
    "default": "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
    "reasoning": [
        "nousresearch/hermes-3-405b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "nvidia/nemotron-3-ultra:free",
        "qwen/qwen3-next-80b-a3b-instruct:free"
    ],
    "coding": [
        "qwen/qwen3-coder-480b-a35b:free",
        "meta-llama/llama-3.3-70b-instruct:free"
    ],
    "thinking": [
        "liquid/lfm2.5-1.2b-thinking:free",
        "qwen/qwen3-next-80b-a3b-instruct:free"
    ],
    "small": [
        "liquid/lfm2.5-1.2b-instruct:free",
        "meta-llama/llama-3.2-3b-instruct:free"
    ]
}

# Image Generation Models (Sourceful)
IMAGE_MODELS = {
    "primary": "sourceful/riverflow-v2.5-pro:free",
    "fast": "sourceful/riverflow-v2.5-fast:free",
    "fallback": "moondream"
}

# Embedding Model
HF_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_MODEL_SPEC = "nvidia/llama-nemotron-embed-vl-1b-v2:free"

# Model tiers used by agent logic
MODEL_TIERS = {
    "smart_tasks": LOCAL_MODELS,
    "standard_tasks": [CLOUD_FREE_MODELS["default"]] + CLOUD_FREE_MODELS["thinking"],
    "complex_tasks": CLOUD_FREE_MODELS["reasoning"],
    "coding_tasks": CLOUD_FREE_MODELS["coding"]
}

# Task classification keywords for auto-routing
TASK_ROUTING = {
    "smart_tasks": [
        "greeting", "status_check", "time_query", "mood", "idle_chat", 
        "simple_question", "hi", "hello", "hey", "what's up", "how are you"
    ],
    "standard_tasks": [
        "analysis", "summarize", "translate", "explain", "write",
        "learn", "search"
    ],
    "coding_tasks": [
        "code", "debug", "review", "refactor", "test", "document", "python", "script"
    ],
    "complex_tasks": [
        "agent_control", "complex_reasoning", "research", "planning", 
        "orchestration", "architecture", "design", "autonomous"
    ]
}

# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS LOADER
# ═══════════════════════════════════════════════════════════════════════════════

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

def load_settings() -> Dict:
    if not os.path.exists(SETTINGS_PATH):
        return {}
    try:
        with open(SETTINGS_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading settings.json: {e}")
        return {}

_settings = load_settings()

# ═══════════════════════════════════════════════════════════════════════════════
# MULTI-API KEY MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

# API Keys from settings or environment
# Can be a string or a list of strings for rotation
_KEYS = _settings.get("api_keys", {})

def get_api_key(provider: str) -> Optional[str]:
    """Get an API key for a provider. Supports single keys or lists (random rotation)."""
    import random
    
    # Check settings first, then environment
    keys = _KEYS.get(provider) or os.getenv(f"{provider.upper()}_API_KEY")
    
    if not keys:
        # Fallback for specific environment naming conventions
        if provider == "google": keys = os.getenv("GEMINI_API_KEY")
        elif provider == "openai": keys = os.getenv("OPENAI_API_KEY")
        elif provider == "anthropic": keys = os.getenv("ANTHROPIC_API_KEY")
        elif provider == "openrouter": keys = os.getenv("OPENROUTER_API_KEY")

    if isinstance(keys, list) and keys:
        return random.choice(keys)
    return keys

# API Keys (for quick access)
OPENROUTER_API_KEY = get_api_key("openrouter")
GEMINI_API_KEY = get_api_key("google")
OPENAI_API_KEY = get_api_key("openai")
ANTHROPIC_API_KEY = get_api_key("anthropic")
HF_TOKEN = get_api_key("huggingface") or os.getenv("HF_TOKEN")
if HF_TOKEN:
    os.environ["HF_TOKEN"] = HF_TOKEN

# ═══════════════════════════════════════════════════════════════════════════════
# MODEL CONFIGURATION (with settings.json fallback)
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_MODEL = _settings.get("models", {}).get("default", CLOUD_FREE_MODELS["default"])
FAST_MODEL    = _settings.get("models", {}).get("fast", LOCAL_MODELS[0])
VISION_MODEL  = _settings.get("models", {}).get("vision", IMAGE_MODELS["fallback"])
EMBEDDING_MODEL = _settings.get("models", {}).get("embedding", HF_EMBEDDING_MODEL)

# Ollama & API endpoints
OLLAMA_BASE_URL = _settings.get("server", {}).get("ollama_base_url", "http://localhost:11434")
OPENAI_BASE_URL = _settings.get("server", {}).get("openai_base_url", "https://api.openai.com/v1")
OPENROUTER_BASE_URL = _settings.get("server", {}).get("openrouter_base_url", "https://openrouter.ai/api/v1")

os.environ["OLLAMA_HOST"] = OLLAMA_BASE_URL

# ═══════════════════════════════════════════════════════════════════════════════
# SERVER CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

HOST            = _settings.get("server", {}).get("host", "0.0.0.0")
PORT            = _settings.get("server", {}).get("port", 5069)
RAG_PORT        = _settings.get("server", {}).get("rag_port", 5080)
MODULEFLOW_PORT = 5070
TODO_PORT       = 5000
UPLOAD_FOLDER   = "static/uploads"

# ═══════════════════════════════════════════════════════════════════════════════
# SESSION CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

POMODORO_WORK_MINUTES  = 25
POMODORO_BREAK_MINUTES = 5
POMODORO_LONG_BREAK    = 15
MEMORY_MAX_MESSAGES    = 50

# ═══════════════════════════════════════════════════════════════════════════════
# APP LAUNCHER CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

APPS: Dict[str, List[str]] = {
    "chrome":           ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"],
    "brave":            ["brave-browser", "brave"],
    "firefox":          ["firefox", "firefox-esr"],
    "edge":             ["microsoft-edge", "microsoft-edge-stable"],
    "opera":            ["opera"],
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
    "terminal":         ["ghostty", "konsole", "xterm", "alacritty", "kitty", "tilix"],
    "konsole":          ["konsole"],
    "alacritty":        ["alacritty"],
    "kitty":            ["kitty"],
    "file manager":     ["nautilus", "dolphin", "thunar", "nemo", "pcmanfm"],
    "files":            ["nautilus", "dolphin", "thunar", "nemo"],
    "task manager":     ["gnome-system-monitor", "ksysguard", "htop", "btop"],
    "calculator":       ["gnome-calculator", "kcalc", "galculator", "qalculate-gtk"],
    "text editor":      ["gedit", "kate", "mousepad", "xed"],
    "settings":         ["gnome-control-center", "systemsettings5", "xfce4-settings-manager"],
    "screenshot":       ["gnome-screenshot", "spectacle", "flameshot"],
    "vlc":              ["vlc"],
    "mpv":              ["mpv"],
    "rhythmbox":        ["rhythmbox"],
    "spotify":          ["spotify"],
    "obs":              ["obs"],
    "audacity":         ["audacity"],
    "gimp":             ["gimp"],
    "inkscape":         ["inkscape"],
    "libreoffice":      ["libreoffice"],
    "writer":           ["libreoffice", "--writer"],
    "calc":             ["libreoffice", "--calc"],
    "impress":          ["libreoffice", "--impress"],
    "postman":          ["postman"],
    "dbeaver":          ["dbeaver"],
    "docker":           ["docker"],
    "virtualbox":       ["virtualbox"],
    "discord":          ["discord", "Discord"],
    "telegram":         ["telegram-desktop", "Telegram"],
    "slack":            ["slack"],
    "zoom":             ["zoom"],
    "teams":            ["teams", "teams-for-linux"],
    "whatsapp":         ["whatsapp-for-linux"],
    "claude code":      ["claude"],
    "gemini cli":       ["gemini"],
    "opencode":         ["opencode"],
    "kiro":             ["kiro-cli"],
}

WEB_APPS: Dict[str, str] = {
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
    "openrouter":       "https://openrouter.ai",
    "huggingface":      "https://huggingface.co",
}

def _find_cmd(candidates: List[str]) -> Optional[List[str]]:
    if len(candidates) >= 2 and candidates[0].startswith("libreoffice"):
        if shutil.which("libreoffice"):
            return candidates
        return None
    for cmd in candidates:
        if shutil.which(cmd):
            return [cmd]
    return None

def launch_app(name: str) -> str:
    key = name.lower().strip()
    if key in APPS:
        cmd = _find_cmd(APPS[key])
        if cmd:
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return f"Opening {name}~ ✨"
            except Exception as e:
                return f"Found {name} but couldn't launch it: {e}"
        else:
            if key in WEB_APPS:
                return _open_url(WEB_APPS[key], name)
            return f"I couldn't find {name} installed. Try: sudo apt install {APPS[key][0]}"
    if key in WEB_APPS:
        return _open_url(WEB_APPS[key], name)
    if shutil.which(key):
        try:
            subprocess.Popen([key], stdout=open('logs/tool_execution.log', 'a'), stderr=open('logs/tool_execution.log', 'a'), start_new_session=True)
            return f"Opening {name}~ ✨"
        except Exception as e:
            return f"Tried to open {name} but got: {e}"
    return f"I don't know how to open '{name}' yet. Add it to config.py!"

def _open_url(url: str, label: str) -> str:
    try:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return f"Opening {label} in your browser~ 🌐"
    except FileNotFoundError:
        import webbrowser
        webbrowser.open(url)
        return f"Opening {label}~ 🌐"
    except Exception as e:
        return f"Couldn't open {label}: {e}"

# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL & EXTERNAL SERVICES
# ═══════════════════════════════════════════════════════════════════════════════

EMAIL_SENDER = _settings.get("email", {}).get("sender", os.getenv("EMAIL_SENDER", os.getenv("GMAIL_ADDRESS", "")))
EMAILS: Dict[str, str] = {}

# ═══════════════════════════════════════════════════════════════════════════════
# DOCKER & CONTAINER ORCHESTRATION CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

DOCKER_SOCKET = "/var/run/docker.sock"
DOCKER_ENABLED = os.path.exists(DOCKER_SOCKET)

# Marin's managed container labels
MARIN_CONTAINER_LABEL = "marin.managed=true"
MARIN_OWNER_LABEL = "marin.owner=bayazid"

# ═══════════════════════════════════════════════════════════════════════════════
# PROACTIVE ENGINE INTERVALS (Updated as requested)
# ═══════════════════════════════════════════════════════════════════════════════

PROACTIVE_INTERVALS = {
    "idle_checks": [1800, 7200, 25200, 172800],  # 30min, 2hr, 7hr, 2d
    "active_user_multiplier": 0.5,  # Halve intervals when user is active
    "inactive_user_multiplier": 2.0,  # Double intervals when user is inactive
    "quiet_hours": {"start": 0, "end": 7.5},  # Midnight to 7:30 AM
}

# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK & FORENSICS CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

HEALTH_CHECK_INTERVAL = 600  # 10 minutes
MAX_FORENSICS_PER_HOUR = 5
FORENSIC_WINDOW_SECONDS = 3600

# ═══════════════════════════════════════════════════════════════════════════════
# MCP / AGENT DISCOVERY CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

MCP_AGENTS = {
    "claude": "Claude Code",
    "gemini": "Gemini CLI",
    "opencode": "OpenCode",
    "kiro-cli": "Kiro CLI",
    "aider": "Aider",
    "cursor": "Cursor",
    "windsurf": "Windsurf",
    "copilot": "GitHub Copilot CLI",
}

# ═══════════════════════════════════════════════════════════════════════════════
# API PROVIDERS LIST (for .bashrc)
# ═══════════════════════════════════════════════════════════════════════════════

API_PROVIDERS = {
    "openrouter": "OpenRouter (free models + paid)",
    "gemini": "Google Gemini (free tier available)",
    "openai": "OpenAI GPT models",
    "anthropic": "Anthropic Claude models",
    "telegram": "Telegram Bot API",
    "ollama": "Local Ollama (free, offline)",
    "huggingface": "HuggingFace Inference API",
    "replicate": "Replicate API",
    "together": "Together.ai",
    "perplexity": "Perplexity API",
    "groq": "Groq (fast inference)",
    "cerebras": "Cerebras (fast inference)",
    "fireworks": "Fireworks AI",
    "deepinfra": "DeepInfra",
    "anthropic-direct": "Anthropic Direct API",
}

# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_available_providers() -> List[str]:
    """Get list of API providers that have keys configured."""
    available = ["ollama"]  # Always available locally
    providers_with_keys = ["google", "openai", "anthropic", "openrouter"]
    for p in providers_with_keys:
        if get_api_key(p):
            available.append(p)
    return list(set(available))

def classify_task(user_input: str) -> str:
    """Classify user input to determine model tier."""
    text = user_input.lower().strip()
    for tier, keywords in TASK_ROUTING.items():
        for keyword in keywords:
            if keyword in text:
                return tier
    # Default to standard for ambiguous queries
    return "standard_tasks"

def get_model_for_task(task_type: str, force_tier: Optional[str] = None) -> str:
    """Get optimal model for a given task type."""
    tier = force_tier or task_type
    models = MODEL_TIERS.get(tier, [])
    
    if not models:
        return DEFAULT_MODEL
    
    import random
    return random.choice(models)

def get_api_providers_comment() -> str:
    """Generate comment string for .bashrc with all available providers."""
    providers_str = ", ".join(sorted(API_PROVIDERS.keys()))
    return f"# Available API providers: {providers_str}"
