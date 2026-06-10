import asyncio
import re
import os

# Piper binary and voice paths inside the container
PIPER_BIN = "/app/utils/piper/piper"
VOICE_PATH = "/root/.piper-voices/en_US-amy-medium.onnx"

async def _run_piper(text: str):
    if not os.path.exists(PIPER_BIN):
        print(f"❌ Piper binary not found at {PIPER_BIN}")
        return
    
    # Clean text to prevent shell injection or broken speech
    safe_text = text.replace("'", "").replace('"', "")
    
    # OWNER-ONLY — single-user dev box
    cmd = f"echo '{safe_text}' | {PIPER_BIN} --model {VOICE_PATH} --output_raw | aplay -r 22050 -f S16_LE -t raw"
    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
    except Exception as e:
        print(f"❌ Voice playback failed: {e}")

def _clean(text: str) -> str:
    text = re.sub(r"\*{1,3}[\s\S]{0,2000}?\*{1,3}", "", text)
    text = re.sub(r"_{1,2}[\s\S]{0,2000}?_{1,2}", "", text)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"https?://\S+", "", text)
    return " ".join(text.split()).strip()

async def speak_male(text: str):
    await _run_piper(_clean(text))

async def speak_female(text: str):
    await _run_piper(_clean(text))

def init():
    pass
