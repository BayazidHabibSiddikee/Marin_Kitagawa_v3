"""
utils/tts.py — Text-to-Speech for Marin

Priority order:
  1. gTTS (Google TTS, online, female voice, no RAM usage) ← PRIMARY
  2. Piper (local fallback, requires binary + model)

gTTS produces MP3; we convert to WAV in-memory with pydub so the rest of
the pipeline (lipsync, browser playback) stays identical.
"""
import asyncio
import io
import os
import re
import wave
from typing import Optional

import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPER_BIN  = os.path.join(BASE_DIR, "utils", "piper", "piper")
_PIPER_VOICE = os.path.expanduser("~/.piper-voices/en_US-amy-medium.onnx")

SAMPLE_RATE = 22050   # gTTS → pydub output sample rate


# ── Text cleaning ─────────────────────────────────────────────────────────────
def _clean(text: str) -> str:
    """Strip markdown, code blocks, and URLs before sending to TTS."""
    text = re.sub(r"\*{1,3}[\s\S]{0,2000}?\*{1,3}", "", text)
    text = re.sub(r"_{1,2}[\s\S]{0,2000}?_{1,2}", "", text)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[#*`~|]", "", text)
    return " ".join(text.split()).strip()


# ── gTTS → WAV (synchronous, runs in thread) ─────────────────────────────────
def _gtts_to_wav(text: str) -> bytes:
    """
    Generate speech using Google TTS (female en voice) and return WAV bytes.
    Converts the MP3 output to WAV using pydub (ffmpeg / libav under the hood).
    """
    try:
        from gtts import gTTS
        from pydub import AudioSegment

        tts = gTTS(text=text, lang="en", tld="com", slow=False)
        mp3_buf = io.BytesIO()
        tts.write_to_fp(mp3_buf)
        mp3_buf.seek(0)

        # Convert MP3 → WAV (mono 22050 Hz, 16-bit PCM)
        segment = AudioSegment.from_file(mp3_buf, format="mp3")
        segment = segment.set_channels(1).set_frame_rate(SAMPLE_RATE).set_sample_width(2)

        wav_buf = io.BytesIO()
        segment.export(wav_buf, format="wav")
        return wav_buf.getvalue()

    except Exception as e:
        print(f"[tts] gTTS failed: {e}")
        return b""


def is_tts_available() -> bool:
    """Return True if gTTS (or Piper fallback) is available."""
    try:
        from gtts import gTTS  # noqa: F401
        return True
    except ImportError:
        pass
    return os.path.isfile(PIPER_BIN) and os.path.isfile(_PIPER_VOICE)


# ── Lipsync schedule generation ───────────────────────────────────────────────
def generate_lipsync_schedule(wav_bytes: bytes, hop_ms: int = 20) -> list[dict]:
    """
    Analyse WAV amplitude and produce a per-frame mouth-open schedule.

    Each frame: { t: float (seconds), open: float (0–1) }
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
    alpha = 0.55
    smoothed[0] = rms[0]
    for i in range(1, len(rms)):
        smoothed[i] = alpha * rms[i] + (1 - alpha) * smoothed[i - 1]

    # Power curve for contrast
    shaped = np.power(smoothed, 0.6)
    shaped = np.clip(shaped * 1.1, 0.0, 0.85)

    # Emit keyframes
    keyframes = []
    prev = -1.0
    hop_s = hop_ms / 1000.0
    for i, v in enumerate(shaped):
        v = round(float(v), 3)
        if abs(v - prev) >= 0.03:
            keyframes.append({"t": round(i * hop_s, 3), "open": v})
            prev = v

    total_s = round(len(samples) / sr + 0.05, 3)
    keyframes.append({"t": total_s, "open": 0.0})
    return keyframes


# ── Main TTS entry points ──────────────────────────────────────────────────────
async def generate_wav(text: str) -> bytes:
    """Generate WAV bytes from text. Uses gTTS online first, falls back to Piper."""
    clean_text = _clean(text)
    if not clean_text:
        return b""

    # Primary: gTTS (Google, online, female voice, zero RAM)
    try:
        wav = await asyncio.to_thread(_gtts_to_wav, clean_text)
        if wav:
            return wav
    except Exception as e:
        print(f"[tts] gTTS async error: {e}")

    # Fallback: Piper (local)
    return await _generate_wav_piper(clean_text)


async def generate_wav_with_lipsync(text: str) -> tuple[bytes, list[dict]]:
    """
    Generate WAV + compute amplitude-based lipsync schedule in one call.
    Returns (wav_bytes, lipsync_keyframes).
    """
    wav = await generate_wav(text)
    lipsync = generate_lipsync_schedule(wav) if wav else []
    return wav, lipsync


# ── Piper fallback ────────────────────────────────────────────────────────────
async def _generate_wav_piper(text: str) -> bytes:
    """Legacy Piper TTS fallback."""
    if not os.path.isfile(PIPER_BIN):
        print(f"[tts] Piper binary not found at {PIPER_BIN}")
        return b""
    if not os.path.isfile(_PIPER_VOICE):
        print(f"[tts] Piper voice not found at {_PIPER_VOICE}")
        return b""

    cmd = [
        PIPER_BIN,
        "--model", _PIPER_VOICE,
        "--output_file", "-",
        "--length_scale",     "0.9",
        "--noise_scale",      "0.667",
        "--noise_w",          "0.8",
        "--sentence_silence", "0.1",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate(input=text.encode("utf-8"))
        return stdout
    except Exception as e:
        print(f"[tts] Piper failed: {e}")
        return b""


# ── Legacy stubs (keep existing callers working) ──────────────────────────────
async def speak_male(text: str):
    pass


async def speak_female(text: str):
    """Synthesize *text* with the default female gTTS voice."""
    wav = await generate_wav(text)
    if wav:
        await asyncio.to_thread(_play_audio, wav)


def _play_audio(wav_bytes: bytes):
    """Write WAV bytes to a temp file and play with aplay."""
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        path = f.name
    try:
        subprocess.run(["aplay", "-q", path], timeout=60)
    except Exception:
        pass
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def init():
    """No-op for gTTS (no model pre-warming needed). Kept for API compatibility."""
    try:
        from gtts import gTTS  # noqa: F401
        print("[tts] gTTS ready (online Google TTS, female voice)")
    except ImportError:
        print("[tts] gTTS not installed — install with: pip install gTTS pydub")
