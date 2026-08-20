import io
import wave

import numpy as np
import speech_recognition as sr
from faster_whisper import WhisperModel

# --- Configuration ---
MODEL_SIZE = "tiny.en"  # "tiny.en", "base.en", etc.
MODEL_DEVICE = "cpu"    # "cuda" if you have GPU, but tiny runs instantly on CPU
COMPUTE_TYPE = "int8"   # Fast 8-bit inference for CPU

# Global model instance
_model = None

def get_stt_model():
    """Lazy load the Whisper model."""
    global _model
    if _model is None:
        print(f"[STT] Loading {MODEL_SIZE} model on {MODEL_DEVICE}...")
        _model = WhisperModel(MODEL_SIZE, device=MODEL_DEVICE, compute_type=COMPUTE_TYPE)
    return _model


def listen_and_transcribe(timeout: int = 5) -> str:
    """
    Listens to the microphone using automatic Voice Activity Detection (VAD).
    Returns the transcribed text.
    """
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.energy_threshold = 400
    recognizer.pause_threshold = 0.8  # seconds of silence to consider speech complete

    with sr.Microphone() as source:
        print("\n[STT] Adjusting for ambient noise... (1s)")
        recognizer.adjust_for_ambient_noise(source, duration=1)

        print("\n🎤 [STT] Listening... (Speak now)")
        try:
            # timeout: max time to wait for speech to START
            # phrase_time_limit: max length of speech
            audio_data = recognizer.listen(source, timeout=timeout, phrase_time_limit=15)
        except sr.WaitTimeoutError:
            print("[STT] No speech detected.")
            return ""

    print("[STT] Processing audio...")

    # Get raw WAV data from the recognizer
    wav_bytes = audio_data.get_wav_data(convert_rate=16000, convert_width=2)

    # Convert WAV bytes to a float32 numpy array normalized between -1 and 1
    # Faster-whisper expects a 1D numpy array of 16kHz float32
    with io.BytesIO(wav_bytes) as wav_io, wave.open(wav_io, 'rb') as wav_file:
        frames = wav_file.readframes(wav_file.getnframes())
        audio_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

    # Load model
    model = get_stt_model()

    # Transcribe
    segments, info = model.transcribe(audio_np, beam_size=1)

    text = "".join(segment.text for segment in segments).strip()
    return text


def transcribe_audio_bytes(audio_bytes: bytes) -> str:
    """Transcribe an in-memory audio clip (webm/ogg/wav/mp3 — anything ffmpeg/PyAV
    can decode). Used by the web UI's mic button, which uploads a recorded blob."""
    if not audio_bytes:
        return ""
    model = get_stt_model()
    # faster-whisper decodes the container itself via PyAV, so a raw BytesIO works
    segments, _ = model.transcribe(io.BytesIO(audio_bytes), beam_size=1)
    return "".join(segment.text for segment in segments).strip()


if __name__ == "__main__":
    # Quick test if run directly
    print("Testing Speech-to-Text...")
    result = listen_and_transcribe(timeout=10)
    print(f"Result: {result!r}")
