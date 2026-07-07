import asyncio
import os
import re

# Piper binary and voice paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPER_BIN = os.path.join(BASE_DIR, "utils", "piper", "piper")
VOICE_PATH = os.path.expanduser("~/.piper-voices/en_US-amy-medium.onnx")

def _clean(text: str) -> str:
    text = re.sub(r"\*{1,3}[\s\S]{0,2000}?\*{1,3}", "", text)
    text = re.sub(r"_{1,2}[\s\S]{0,2000}?_{1,2}", "", text)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"https?://\S+", "", text)
    return " ".join(text.split()).strip()

async def generate_wav(text: str) -> bytes:
    if not os.path.exists(PIPER_BIN):
        print(f"❌ Piper binary not found at {PIPER_BIN}")
        return b""

    safe_text = _clean(text).replace("'", "").replace('"', "")
    if not safe_text:
        return b""

    cmd = f"echo '{safe_text}' | {PIPER_BIN} --model {VOICE_PATH} --output_file - --length_scale 0.85 --noise_scale 0.8 --noise_w 0.9"
    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await process.communicate()
        return stdout
    except Exception as e:
        print(f"❌ Voice generation failed: {e}")
        return b""

async def speak_male(text: str):
    # Legacy, no longer plays locally via aplay
    pass

async def speak_female(text: str):
    # Legacy, no longer plays locally via aplay
    pass

def init():
    pass
