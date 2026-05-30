import subprocess
import re

VOICE_PATH = "~/.piper-voices/en_US-amy-medium.onnx"

def _run_piper(text: str):
    cmd = f"echo '{text}' | piper-tts --model {VOICE_PATH} --output_raw | aplay -r 22050 -f S16_LE -t raw"
    subprocess.run(cmd, shell=True, capture_output=True)

def _clean(text: str) -> str:
    text = re.sub(r"\*{1,3}[\s\S]{0,2000}?\*{1,3}", "", text)
    text = re.sub(r"_{1,2}[\s\S]{0,2000}?_{1,2}", "", text)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"https?://\S+", "", text)
    return " ".join(text.split()).strip()

def speak_male(text: str):
    _run_piper(_clean(text))

def speak_female(text: str):
    _run_piper(_clean(text))

def init():
    pass