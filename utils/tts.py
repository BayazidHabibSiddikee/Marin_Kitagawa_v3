import asyncio
import base64
import io
import os
import re
import struct
import wave

import numpy as np

# ── Piper binary and voice paths ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPER_BIN = os.path.join(BASE_DIR, "utils", "piper", "piper")

_PRIMARY_VOICE  = os.path.expanduser("~/.piper-voices/en_US-amy-medium.onnx")
_FALLBACK_VOICE = os.path.join(BASE_DIR, "utils", "piper", "en_US-amy-medium.onnx")


def _resolve_voice_path() -> str:
    if os.path.exists(_PRIMARY_VOICE):
        return _PRIMARY_VOICE
    if os.path.exists(_FALLBACK_VOICE):
        return _FALLBACK_VOICE
    return _PRIMARY_VOICE


VOICE_PATH = _resolve_voice_path()


def is_tts_available() -> bool:
    return os.path.isfile(PIPER_BIN) and os.path.isfile(_resolve_voice_path())


# ── Text cleaning ─────────────────────────────────────────────────────────────
def _clean(text: str) -> str:
    """Strip markdown, code blocks, and URLs before sending to TTS."""
    text = re.sub(r"\*{1,3}[\s\S]{0,2000}?\*{1,3}", "", text)
    text = re.sub(r"_{1,2}[\s\S]{0,2000}?_{1,2}", "", text)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[#*`~|]", "", text)
    return " ".join(text.split()).strip()


# ── Lipsync schedule generation ───────────────────────────────────────────────
def generate_lipsync_schedule(wav_bytes: bytes, hop_ms: int = 20) -> list[dict]:
    """
    Analyse WAV amplitude and produce a per-frame mouth-open schedule.

    Each frame: { t: float (seconds), open: float (0–1) }

    Algorithm:
    1. Decode PCM samples from WAV bytes.
    2. Compute RMS energy per hop window (20 ms default → 50 fps).
    3. Normalise to 0–1, apply smoothing and a soft clamp so the
       mouth opens wide on loud vowels and closes fully on silence.
    4. Return only keyframes where the value changes meaningfully
       (delta > 0.03) to minimise payload size.
    """
    if not wav_bytes:
        return []

    try:
        with wave.open(io.BytesIO(wav_bytes)) as w:
            sr        = w.getframerate()
            n_ch      = w.getnchannels()
            sampwidth = w.getsampwidth()
            frames    = w.readframes(w.getnframes())
    except Exception:
        return []

    # Decode samples
    if sampwidth == 2:
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        samples = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        samples = np.frombuffer(frames, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0

    # Mix to mono
    if n_ch > 1:
        samples = samples.reshape(-1, n_ch).mean(axis=1)

    hop = max(1, int(sr * hop_ms / 1000))

    # RMS energy per frame
    n_frames = (len(samples) - hop) // hop + 1
    rms = np.array([
        np.sqrt(np.mean(samples[i * hop:(i + 1) * hop] ** 2))
        for i in range(n_frames)
    ], dtype=np.float32)

    # Normalise
    peak = rms.max()
    if peak < 1e-6:
        return [{"t": 0.0, "open": 0.0}]
    rms = rms / peak

    # Smooth: light EMA so the mouth doesn't jitter frame-to-frame
    smoothed = np.zeros_like(rms)
    alpha = 0.55          # higher = more responsive, lower = smoother
    smoothed[0] = rms[0]
    for i in range(1, len(rms)):
        smoothed[i] = alpha * rms[i] + (1 - alpha) * smoothed[i - 1]

    # Power curve: raises the contrast (makes quiet frames quieter,
    # loud frames louder) so closed-mouth silence looks convincing.
    shaped = np.power(smoothed, 0.6)

    # Clamp to a comfortable VRM range: 0 (closed) – 0.85 (wide open)
    shaped = np.clip(shaped * 1.1, 0.0, 0.85)

    # Emit keyframes — only when value changes by > threshold
    keyframes = []
    prev = -1.0
    hop_s = hop_ms / 1000.0
    for i, v in enumerate(shaped):
        v = round(float(v), 3)
        if abs(v - prev) >= 0.03:
            keyframes.append({"t": round(i * hop_s, 3), "open": v})
            prev = v

    # Always end with mouth closed
    total_s = round(len(samples) / sr + 0.05, 3)
    keyframes.append({"t": total_s, "open": 0.0})

    return keyframes


# ── Main TTS function ─────────────────────────────────────────────────────────
async def generate_wav(text: str) -> bytes:
    """Generate WAV bytes from text using Piper. Returns raw WAV bytes."""
    voice = _resolve_voice_path()

    if not os.path.isfile(PIPER_BIN):
        print(f"❌ Piper binary not found at {PIPER_BIN}")
        return b""
    if not os.path.isfile(voice):
        print(f"❌ Voice model not found at {voice}")
        return b""

    clean_text = _clean(text)
    if not clean_text:
        return b""

    cmd = [
        PIPER_BIN,
        "--model", voice,
        "--output_file", "-",
        "--length_scale",    "0.9",    # slightly slower = more natural, was 0.85
        "--noise_scale",     "0.667",  # Piper default = most natural prosody
        "--noise_w",         "0.8",    # Piper default = best naturalness
        "--sentence_silence", "0.1",   # shorter gap between sentences
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate(input=clean_text.encode("utf-8"))
        return stdout
    except Exception as e:
        print(f"❌ Voice generation failed: {e}")
        return b""


async def generate_wav_with_lipsync(text: str) -> tuple[bytes, list[dict]]:
    """
    Generate WAV + compute amplitude-based lipsync schedule in one call.
    Returns (wav_bytes, lipsync_keyframes).
    """
    wav = await generate_wav(text)
    lipsync = generate_lipsync_schedule(wav) if wav else []
    return wav, lipsync


# ── Legacy stubs ──────────────────────────────────────────────────────────────
async def speak_male(text: str):
    pass

async def speak_female(text: str):
    pass

def init():
    pass
