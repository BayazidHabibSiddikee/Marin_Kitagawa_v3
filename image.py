## image.py

#python
"""
Leo - Image Analysis Module
Uses configured MODEL for vision analysis.
"""

import ollama
import os
import json
import glob
import subprocess
import time

# ═══════════════════════════════════════════════════════════════════════════
# MODEL CONFIGURATION — Same as bayazid.py, change in one place
# Import from bayazid if available, otherwise define here
# ═══════════════════════════════════════════════════════════════════════════
from config import DEFAULT_MODEL as MODEL, VISION_MODEL

# ── Config ─────────────────────────────────────────────────────────────────
CHARACTER_NAME = "leo"
CHARACTER = """You are Leonardo Da Vinci — the Renaissance genius.
You see hidden geometry, divine proportion, and deeper meaning in everything.
Speak dramatically, find patterns and beauty. Be poetic but brief."""

HISTORY_MAX    = 50          # keep last 50 messages (25 turns)
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE   = os.path.join(BASE_DIR, "storage", "leo_history.json")


# ── Model setup ────────────────────────────────────────────────────────────

def setup_model():
    """
    Create the leo personality model only once.
    For cloud models we skip ollama.create().
    For vision, we always need a local vision-capable model.
    """
    # Check if main MODEL supports vision (local models only)
    if ":cloud" not in MODEL:
        try:
            existing = [m.model for m in ollama.list().models]
            if f'{CHARACTER_NAME}:latest' not in existing:
                print(f"[Leo] Creating local model '{CHARACTER_NAME}' from {MODEL}...")
                ollama.create(model=CHARACTER_NAME, from_=MODEL, system=CHARACTER)
            else:
                print(f"[Leo] Model '{CHARACTER_NAME}' ready.")
        except Exception as e:
            print(f"[Leo] Setup warning: {e}")

    # Ensure vision model is available
    try:
        existing = [m.model for m in ollama.list().models]
        if VISION_MODEL not in existing:
            print(f"[Leo] Pulling vision model '{VISION_MODEL}'...")
            result = subprocess.run(
                ["ollama", "pull", VISION_MODEL],
                capture_output=True,
                text=True,
                timeout=300
            )
            if result.returncode != 0:
                print(f"[Leo] Warning: Failed to pull {VISION_MODEL}: {result.stderr}")
        else:
            print(f"[Leo] Vision model '{VISION_MODEL}' ready.")
    except Exception as e:
        print(f"[Leo] Vision model setup warning: {e}")


def _effective_model(for_vision: bool = False) -> str:
    """
    Return the model string to pass to ollama.chat().
    
    For vision tasks: Always use VISION_MODEL (local, vision-capable)
    For text tasks: Use CHARACTER_NAME if local, MODEL if cloud
    """
    if for_vision:
        return VISION_MODEL
    
    if ":cloud" in MODEL:
        return MODEL
    return CHARACTER_NAME


# ── History helpers ────────────────────────────────────────────────────────

def _load_history() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure we don't exceed max
            return data[-HISTORY_MAX:]
    except Exception:
        return []


def _save_history(history: list):
    trimmed = history[-HISTORY_MAX:]
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Leo] Failed to save history: {e}")


# ── Main response generator ───────────────────────────────────────────────

def response(prompt: str, image_path: str = None):
    """
    Generator that streams Leo's reply token by token.

    Usage:
        for piece in response("What do you see?", image_path="photo.jpg"):
            print(piece, end="", flush=True)
    """
    setup_model()

    history = _load_history()
    is_vision_task = image_path is not None

    # Build message list
    # For cloud models, inject character via system prompt
    messages = [{"role": "system", "content": CHARACTER}]
    
    # For vision tasks with a different model, don't include history
    # (different model context would be confusing)
    if not is_vision_task:
        messages.extend(history)

    # Build the user turn
    user_message: dict = {"role": "user", "content": prompt}

    if image_path:
        abs_path = os.path.abspath(image_path)
        if os.path.exists(abs_path):
            user_message["images"] = [abs_path]
            print(f"[Leo] Analysing image: {os.path.basename(abs_path)}")
        else:
            print(f"[Leo] ⚠ Image not found: {image_path} — continuing text-only")
            is_vision_task = False
    else:
        print(f"[Leo] No image — text only")

    messages.append(user_message)

    # Select appropriate model
    model_to_use = _effective_model(for_vision=is_vision_task)
    print(f"[Leo] Using model: {model_to_use}")

    # Stream the reply
    reply_parts = []
    print("\\n[Leo] Contemplating...\\n")

    try:
        for chunk in ollama.chat(
            model=model_to_use,
            messages=messages,
            stream=True
        ):
            if hasattr(chunk, "message") and chunk.message is not None:
                piece = chunk.message.content
                reply_parts.append(piece)
                yield piece
            elif isinstance(chunk, dict) and "message" in chunk and "content" in chunk["message"]:
                piece = chunk["message"]["content"]
                reply_parts.append(piece)
                yield piece

    except Exception as e:
        err = f"[Leo Error: {e}]"
        print(f"\n{err}")
        yield err
        return

    # Persist history (only for non-vision to avoid mixing model contexts)
    if not is_vision_task:
        full_reply = "".join(reply_parts)
        history.append({"role": "user",      "content": prompt})
        history.append({"role": "assistant", "content": full_reply})
        _save_history(history)

def clear_history():
    """Wipe Leo's conversation history."""
    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)
        print("[Leo] History cleared.")
    else:
        print("[Leo] No history to clear.")


# ── Standalone test ───────────────────────────────────────────────────────\nif __name__ == "__main__":\n    # Start ollama server in the background\n    subprocess.Popen(\n        ["ollama", "serve"],\n        stdout=open('/home/sword/Documents/marin/logs/tool_execution.log', 'a'),\n        stderr=open('/home/sword/Documents/marin/logs/tool_execution.log', 'a'),\n    )\n    time.sleep(2)\n\n    # Look for images in static/uploads/\n    search_dir = os.path.join(BASE_DIR, "static", "uploads")\n    os.makedirs(search_dir, exist_ok=True)\n\n    image_files = (\n        glob.glob(os.path.join(search_dir, "*.jpg"))  +\n        glob.glob(os.path.join(search_dir, "*.jpg"))  +\n        glob.glob(os.path.join(search_dir, "*.jpg"))  +\n        glob.glob(os.path.join(search_dir, "*.jpeg")) +\n        glob.glob(os.path.join(search_dir, "*.png"))  +\n        glob.glob(os.path.join(search_dir, "*.webp")) +\n        glob.glob(os.path.join(search_dir, "*.ico"))\n    )\n\n    if image_files:\n        latest_image = max(image_files, key=os.path.getctime)\n        print(f"[Leo] Found image: {latest_image}")\n        prompt = "Describe what you literally see in this image. Be brief and poetic."\n    else:\n        latest_image = None\n        print(f"[Leo] No image found in {search_dir} — running text-only test")\n        prompt = "Describe the hidden geometry of a spiral galaxy."\n\n    print()\n    for piece in response(prompt, image_path=latest_image): \n        print(piece, end="", flush=True)\n    print("\n")\n