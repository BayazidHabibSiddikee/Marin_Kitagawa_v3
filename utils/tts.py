import asyncio
import io
import os
import re
import wave
from typing import Optional

import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIBEVOICE_ROOT = os.environ.get(
    "VIBEVOICE_PATH",
    os.path.expanduser("~/Documents/VibeVoice"),
)
MODEL_HF_ID   = "microsoft/VibeVoice-Realtime-0.5B"
_FEMALE_VOICE = "en-Grace_woman"          # built-in female preset
PIPER_BIN     = os.path.join(BASE_DIR, "utils", "piper", "piper")
_PIPER_VOICE  = os.path.expanduser("~/.piper-voices/en_US-amy-medium.onnx")

SAMPLE_RATE   = 24000                     # VibeVoice output sample rate


# ── Global singleton (loaded lazily on first call) ────────────────────────────
_model: Optional["torch.nn.Module"] = None
_processor = None
_device: str = "cpu"


def _get_device() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _load_model() -> bool:
    """Lazily load the VibeVoice model + processor + voice cache. Returns True on success."""
    global _model, _processor, _device

    if _model is not None:
        return True

    try:
        import torch
        from huggingface_hub import snapshot_download
        from vibevoice.modular.modeling_vibevoice_streaming_inference import (
            VibeVoiceStreamingForConditionalGenerationInference,
        )
        from vibevoice.processor.vibevoice_streaming_processor import (
            VibeVoiceStreamingProcessor,
        )
        from transformers.cache_utils import DynamicCache
        from transformers.modeling_outputs import BaseModelOutputWithPast
    except ImportError as e:
        print(f"[tts] VibeVoice dependency missing — {e}")
        return False

    _device = _get_device()
    load_dtype = torch.float32 if _device != "cuda" else torch.bfloat16
    attn_impl  = "sdpa"          # works on CPU / MPS / CUDA

    # Download model weights locally if not already present
    cache_dir = os.path.join(
        os.path.expanduser("~/.cache/huggingface/hub"),
        f"models--{MODEL_HF_ID.replace('/', '--')}",
    )
    if not os.path.exists(os.path.join(cache_dir, "config.json")):
        print(f"[tts] Downloading {MODEL_HF_ID} … (this may take a while)")
        snapshot_download(MODEL_HF_ID, local_dir=cache_dir)

    try:
        _processor = VibeVoiceStreamingProcessor.from_pretrained(cache_dir)

        _model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
            cache_dir,
            dtype=load_dtype,
            device_map=_device if _device != "cpu" else None,
            attn_implementation=attn_impl,
        )
        if _device == "mps":
            _model.to("mps")
        _model.eval()
        _model.set_ddpm_inference_steps(num_steps=5)

        # Load female voice cache
        voice_file = _resolve_voice(_FEMALE_VOICE)
        if voice_file and os.path.isfile(voice_file):
            with torch.serialization.safe_globals(
                [BaseModelOutputWithPast, DynamicCache]
            ):
                _voice_cache = torch.load(
                    voice_file, map_location=_device, weights_only=False,
                )
        else:
            print(f"[tts] Warning: female voice not found at {voice_file}, using null cache")
            _voice_cache = None

        _model._voice_cache = _voice_cache
        print(f"[tts] VibeVoice loaded on {_device}  ({load_dtype})")
        return True
    except Exception as e:
        print(f"[tts] Failed to load VibeVoice: {e}")
        import traceback
        traceback.print_exc()
        _model = None
        return False


def _resolve_voice(speaker_name: str) -> Optional[str]:
    """Find a .pt voice file matching *speaker_name* under VibeVoice demo/voices."""
    voices_dir = os.path.join(VIBEVOICE_ROOT, "demo", "voices", "streaming_model")
    if not os.path.isdir(voices_dir):
        return None
    name = speaker_name.lower()
    for fname in sorted(os.listdir(voices_dir)):
        if fname.lower().startswith(name):
            return os.path.join(voices_dir, fname)
    # fallback: first woman file
    for fname in sorted(os.listdir(voices_dir)):
        if "woman" in fname.lower() or "female" in fname.lower():
            return os.path.join(voices_dir, fname)
    return None


def is_tts_available() -> bool:
    """Return True if either VibeVoice or Piper is available."""
    try:
        if _load_model():
            return True
    except Exception:
        pass
    return os.path.isfile(PIPER_BIN) and os.path.isfile(_PIPER_VOICE)


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


# ── Main TTS function ─────────────────────────────────────────────────────────
async def generate_wav(text: str) -> bytes:
    """Generate WAV bytes from text using VibeVoice (falls back to Piper)."""
    clean_text = _clean(text)
    if not clean_text:
        return b""

    # Try VibeVoice first
    try:
        imports_ok = await asyncio.to_thread(_check_imports)
        if imports_ok and _load_model():
            wav = await asyncio.to_thread(_generate_wav_vibevoice, clean_text)
            if wav:
                return wav
    except Exception as e:
        print(f"[tts] VibeVoice error: {e}")

    # Fall back to Piper
    return await _generate_wav_piper(clean_text)


def _check_imports() -> bool:
    """Import guard called inside to_thread so it never blocks the event loop."""
    try:
        import torch                        # noqa: F401
        from vibevoice.modular.modeling_vibevoice_streaming_inference import (  # noqa: F401
            VibeVoiceStreamingForConditionalGenerationInference,
        )
        from vibevoice.processor.vibevoice_streaming_processor import (  # noqa: F401
            VibeVoiceStreamingProcessor,
        )
        return True
    except ImportError:
        return False


def _generate_wav_vibevoice(text: str) -> bytes:
    """Run synchronous VibeVoice inference and return WAV bytes."""
    import torch
    import copy
    from transformers.cache_utils import DynamicCache
    from transformers.modeling_outputs import BaseModelOutputWithPast

    # Prepare inputs
    inputs = _processor.process_input_with_cached_prompt(
        text=text,
        cached_prompt=_model._voice_cache,
        padding=True,
        return_tensors="pt",
        return_attention_mask=True,
    )
    for k, v in inputs.items():
        if torch.is_tensor(v):
            inputs[k] = v.to(_device)

    with torch.no_grad():
        outputs = _model.generate(
            **inputs,
            max_new_tokens=None,
            cfg_scale=1.5,
            tokenizer=_processor.tokenizer,
            generation_config={"do_sample": False},
            verbose=False,
            all_prefilled_outputs=copy.deepcopy(_model._voice_cache)
                                  if _model._voice_cache is not None else None,
        )

    if not outputs.speech_outputs or outputs.speech_outputs[0] is None:
        return b""

    audio_tensor = outputs.speech_outputs[0]
    audio_np = audio_tensor.float().detach().cpu().numpy()
    if audio_np.ndim > 1:
        audio_np = audio_np.squeeze()

    return _numpy_to_wav_bytes(audio_np)


def _numpy_to_wav_bytes(audio_np: np.ndarray) -> bytes:
    """Convert float32 numpy array to in-memory WAV bytes (PCM 16-bit, mono)."""
    audio_np = np.clip(audio_np, -1.0, 1.0)
    pcm = (audio_np * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


async def _generate_wav_piper(text: str) -> bytes:
    """Legacy Piper TTS fallback (same interface as before)."""
    if not os.path.isfile(PIPER_BIN):
        print(f"❌ Piper binary not found at {PIPER_BIN}")
        return b""
    if not os.path.isfile(_PIPER_VOICE):
        print(f"❌ Piper voice not found at {_PIPER_VOICE}")
        return b""

    cmd = [
        PIPER_BIN,
        "--model", _PIPER_VOICE,
        "--output_file", "-",
        "--length_scale",    "0.9",
        "--noise_scale",     "0.667",
        "--noise_w",         "0.8",
        "--sentence_silence", "0.1",
    ]
    try:
        proc = asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate(input=text.encode("utf-8"))
        return stdout
    except Exception as e:
        print(f"❌ Piper voice generation failed: {e}")
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
    """Synthesize *text* with the default female VibeVoice preset (en-Grace)."""
    wav = await generate_wav(text)
    if wav:
        await asyncio.to_thread(_play_audio, wav)


def _play_audio(wav_bytes: bytes):
    """Write WAV bytes to a temp file and play with aplay."""
    import subprocess, tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        path = f.name
    try:
        subprocess.run(["aplay", "-q", path], timeout=60)
    except Exception:
        pass
    finally:
        os.unlink(path)


def init():
    """Pre-warm the VibeVoice model (call at server startup for faster first response)."""
    _load_model()
