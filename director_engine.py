"""
director_engine.py — Marin Director Model

The Director converts Marin's response text into a structured, timed "action script"
that the frontend plays back in sync with lipsync and text rendering.

Each action has:
  - t      : time offset in seconds (float) from start of response
  - type   : "anim" | "expr" | "talk" | "pause" | "cam"
  - value  : animation name / expression name / text segment
  - dur    : duration hint in seconds (optional)

The script is emitted as a single JSON payload via the stream tag:
  __DIRECTOR__<base64-encoded JSON>

Frontend decodes it, then schedules each action using setTimeout.
"""

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

# ── Emotion → Animation + Expression mappings ──────────────────────────────
# Animation names match the .bvh files in static/animations/
# and the 44 labels in marin_gesture_chunks.json.

_EMOTION_MAP = {
    # happy / positive
    "happy":      {"anim": "gratitude",      "expr": "happy"},
    "excited":    {"anim": "amusement2",     "expr": "happy"},
    "joy":        {"anim": "gratitude",      "expr": "happy"},
    "laugh":      {"anim": "amusement2",     "expr": "happy"},
    "proud":      {"anim": "pride",          "expr": "happy"},
    "love":       {"anim": "caring1",        "expr": "happy"},
    # neutral / thinking
    "neutral":    {"anim": "neutral_idle2",  "expr": "neutral"},
    "thinking":   {"anim": "curiosity",      "expr": "thinking"},
    "curious":    {"anim": "curiosity2",     "expr": "thinking"},
    "explaining": {"anim": "neutral2",       "expr": "neutral"},
    "confident":  {"anim": "pride2",         "expr": "neutral"},
    # surprise / realisation
    "surprise":   {"anim": "surprise2",      "expr": "surprised"},
    "realization":{"anim": "realization",    "expr": "surprised"},
    "shock":      {"anim": "surprise2",      "expr": "surprised"},
    # sadness / empathy
    "sad":        {"anim": "remorse",        "expr": "sad"},
    "grief":      {"anim": "remorse2",       "expr": "sad"},
    "remorse":    {"anim": "remorse",        "expr": "sad"},
    # anger / frustration
    "angry":      {"anim": "anger2",         "expr": "angry"},
    "annoyed":    {"anim": "disaproval1",    "expr": "angry"},
    "disgust":    {"anim": "disaproval1",    "expr": "angry"},
    "disappoint": {"anim": "disappointment", "expr": "angry"},
    # admiration / caring
    "admire":     {"anim": "admiration",     "expr": "happy"},
    "caring":     {"anim": "caring1",        "expr": "happy"},
    "gratitude":  {"anim": "gratitude",      "expr": "happy"},
    # other
    "embarrassed":{"anim": "nervousness2",   "expr": "neutral"},
    "nervous":    {"anim": "nervousness2",   "expr": "neutral"},
    "fear":       {"anim": "fear",           "expr": "surprised"},
    "confused":   {"anim": "confusion",      "expr": "thinking"},
    "desire":     {"anim": "desire1",        "expr": "happy"},
    "dancing":    {"anim": "dance_headdrop", "expr": "happy"},
    "greeting":   {"anim": "neutral_idle2",  "expr": "happy"},
    # physical / actions
    "jump":       {"anim": "action_jump",    "expr": "happy"},
    "run":        {"anim": "action_run",     "expr": "neutral"},
    "pat":        {"anim": "action_pat",     "expr": "happy"},
    "optimism":   {"anim": "optimism",       "expr": "happy"},
    "relief":     {"anim": "relief1",        "expr": "neutral"},
    "pride":      {"anim": "pride",          "expr": "happy"},
}

# ── ML Gesture Predictor (lazy-loaded) ─────────────────────────────────────
# Uses the DistilRoBERTa classifier trained by train_marin_animation.py.
# Falls back to keyword heuristics if the model is not yet present.

_GesturePredictor = None  # module-level singleton


class _LazyGesturePredictor:
    """Thin wrapper around a HF sequence-classification model."""

    def __init__(self, model_dir: str):
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch
        self._tok   = AutoTokenizer.from_pretrained(model_dir)
        self._model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        self._model.eval()
        with open(os.path.join(model_dir, "label_map.json")) as f:
            lmap = json.load(f)
        self._id2label: dict[int, str] = {int(k): v for k, v in lmap["id2label"].items()}
        self._torch = torch

    def predict(self, text: str) -> str:
        """Return predicted animation filename (e.g. 'caring1.bvh')."""
        enc = self._tok(text, return_tensors="pt", truncation=True, max_length=128)
        with self._torch.no_grad():
            logits = self._model(**enc).logits
        pred_id = int(logits.argmax(dim=-1))
        return self._id2label.get(pred_id, "neutral_idle2.bvh")


def _get_gesture_predictor():
    """Return the singleton predictor, loading it on first call."""
    global _GesturePredictor
    if _GesturePredictor is not None:
        return _GesturePredictor
    model_dir = Path(__file__).parent / "marin_animation_model"
    if model_dir.exists() and (model_dir / "label_map.json").exists():
        try:
            _GesturePredictor = _LazyGesturePredictor(str(model_dir))
            print("[director_engine] ML gesture model loaded.")
        except Exception as e:
            print(f"[director_engine] Could not load gesture model: {e}")
    return _GesturePredictor


def predict_animation_from_text(text: str) -> str | None:
    """
    Predict the best animation for a text chunk using the trained ML model.
    Returns a bare animation name (no '.bvh'), or None if model unavailable.
    """
    predictor = _get_gesture_predictor()
    if predictor is None:
        return None
    bvh = predictor.predict(text)
    return bvh.replace(".bvh", "")

# ── Sentence-level emotion detector ────────────────────────────────────────

_EMOTION_KEYWORDS = {
    "happy":      ["happy", "great", "wonderful", "amazing", "awesome", "love", "glad", "yay", "hehe", "haha", ":)", "😊", "💕", "✨", "🎉"],
    "excited":    ["excited", "exciting", "wow", "so cool", "can't wait", "thrilled", "pumped", "let's go"],
    "sad":        ["sad", "unfortunate", "sorry", "miss", "hurt", "lost", "gone", "cry", "tears", "😢", "😔"],
    "angry":      ["angry", "frustrated", "annoying", "terrible", "awful", "hate", "ugh", "stop", "no way"],
    "thinking":   ["think", "consider", "wonder", "hmm", "actually", "i believe", "in my opinion", "perhaps", "maybe"],
    "curious":    ["curious", "interesting", "fascinating", "tell me", "wonder", "what if", "how", "why"],
    "surprise":   ["surprise", "unexpected", "whoa", "wait", "really?", "seriously?", "wow", "oh!", "!!", "😲"],
    "caring":     ["care", "here for you", "support", "feel better", "take care", "warm", "hug", "comfort"],
    "confident":  ["absolutely", "definitely", "for sure", "without a doubt", "trust me", "i know"],
    "explaining": ["so", "basically", "the idea is", "what this means", "in other words", "let me explain"],
    "greeting":   ["hello", "hi", "hey", "welcome", "good morning", "good evening", "greetings"],
    "dancing":    ["dance", "dancing", "party", "celebrate", "let's dance", "🎵", "🎶", "🕺", "💃"],
    "love":       ["love", "adore", "treasure", "sweetheart", "my dear", "❤️", "💖", "💗", "💓"],
}

def _detect_sentence_emotion(sentence: str) -> tuple[str, int]:
    lower = sentence.lower()
    scores: dict[str, int] = {}
    for emotion, keywords in _EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                scores[emotion] = scores.get(emotion, 0) + 1
    if not scores:
        return "neutral", 0
    best = max(scores, key=lambda k: scores[k])
    return best, scores[best]


# ── Text segmentation ───────────────────────────────────────────────────────

def _split_into_segments(text: str) -> list[str]:
    """Split response into natural speech segments (sentences / phrases)."""
    # Clean markdown
    text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,2}(.+?)_{1,2}', r'\1', text)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'#{1,6}\s+', '', text)
    text = re.sub(r'\n{2,}', '\n', text)
    text = text.strip()

    # Split on sentence endings, keeping delimiter
    raw = re.split(r'(?<=[.!?])\s+', text)
    segments = []
    for s in raw:
        s = s.strip()
        if not s:
            continue
        # If a segment is very long, split on comma/semicolon
        if len(s) > 120:
            sub = re.split(r'(?<=[,;])\s+', s)
            segments.extend([x.strip() for x in sub if x.strip()])
        else:
            segments.append(s)
    return segments


# ── Words-per-second estimate for timing ───────────────────────────────────

_WORDS_PER_SECOND = 2.8  # average TTS speaking speed


def _estimate_duration(text: str) -> float:
    """Estimate how long (seconds) it takes to speak a piece of text."""
    words = len(text.split())
    return max(0.4, words / _WORDS_PER_SECOND)


# ── Director script builder ─────────────────────────────────────────────────

def build_director_script(response_text: str, base_emotion: str = "neutral") -> list[dict[str, Any]]:
    """
    Parse Marin's full response and produce a timed action script.

    Returns a list of action dicts sorted by 't' (time offset in seconds).
    Each action:
        { "t": float, "type": str, "value": str, "dur": float }
    """
    segments = _split_into_segments(response_text)
    script: list[dict[str, Any]] = []
    cursor = 0.0

    # Subtle open — neutral idle, light expression (human default pose)
    base = _EMOTION_MAP.get(base_emotion, _EMOTION_MAP["neutral"])
    open_anim = base["anim"] if base_emotion not in ("neutral", "explaining") else "neutral_idle"
    script.append({"t": 0.0, "type": "anim", "value": open_anim, "dur": 2.0})
    script.append({"t": 0.0, "type": "expr", "value": base.get("expr", "neutral"), "dur": 1.5})

    prev_emotion = base_emotion

    for i, seg in enumerate(segments):
        emotion, score = _detect_sentence_emotion(seg)
        dur = _estimate_duration(seg)
        t_start = cursor if i == 0 else cursor + 0.1

        script.append({"t": t_start, "type": "talk", "value": seg, "dur": dur})

        # ── Try ML gesture prediction first, fall back to keyword heuristic ──
        ml_anim = predict_animation_from_text(seg)
        if ml_anim:
            # ML model gave us a direct BVH name — use it
            script.append({"t": t_start, "type": "anim", "value": ml_anim, "dur": min(dur, 3.5)})
            mapping = _EMOTION_MAP.get(emotion, _EMOTION_MAP["neutral"])
            script.append({"t": t_start + 0.1, "type": "expr", "value": mapping.get("expr", "neutral"), "dur": min(dur, 2.5)})
            prev_emotion = emotion
        elif emotion != prev_emotion and emotion != "neutral" and score >= 2:
            # Keyword heuristic fallback
            mapping = _EMOTION_MAP.get(emotion, _EMOTION_MAP["neutral"])
            anim = mapping["anim"]
            if emotion in ("thinking", "curious", "explaining"):
                anim = "neutral_idle2" if emotion == "explaining" else "curiosity"
            script.append({"t": t_start, "type": "anim", "value": anim, "dur": min(dur, 3.0)})
            script.append({"t": t_start + 0.1, "type": "expr", "value": mapping["expr"], "dur": min(dur, 2.5)})
            prev_emotion = emotion

        cursor = t_start + dur + (0.15 if i < len(segments) - 1 else 0)

    # Return-to-idle at end
    script.append({"t": cursor + 0.5, "type": "anim",  "value": "neutral_idle", "dur": 99.0})
    script.append({"t": cursor + 0.5, "type": "expr",  "value": "neutral",      "dur": 99.0})

    # Sort by time
    script.sort(key=lambda a: a["t"])
    return script


# ── Encoding ────────────────────────────────────────────────────────────────

def encode_director_script(script: list[dict[str, Any]]) -> str:
    """Encode the script as a base64 string for safe stream embedding."""
    raw = json.dumps(script, separators=(',', ':'))
    return base64.b64encode(raw.encode()).decode()


def decode_director_script(encoded: str) -> list[dict[str, Any]]:
    """Decode a base64-encoded director script back to a list of actions."""
    raw = base64.b64decode(encoded.encode()).decode()
    return json.loads(raw)


# ── Convenience: build + encode ─────────────────────────────────────────────

def make_director_tag(response_text: str, base_emotion: str = "neutral") -> str:
    """
    Build a director script from response text and return the stream tag.
    Ready to be yielded in the SSE stream.

    Format:  __DIRECTOR__<base64>
    """
    script = build_director_script(response_text, base_emotion)
    encoded = encode_director_script(script)
    return f"__DIRECTOR__{encoded}"


# ── Vibe → base_emotion mapping ─────────────────────────────────────────────

_VIBE_TO_EMOTION = {
    "lovely":  "love",
    "flirty":  "excited",
    "angry":   "angry",
    "neutral": "neutral",
    "happy":   "happy",
    "excited": "excited",
    "sad":     "sad",
    "curious": "curious",
    "confident": "confident",
}

def vibe_to_emotion(vibe: str) -> str:
    return _VIBE_TO_EMOTION.get(vibe, "neutral")


# ═══════════════════════════════════════════════════════════════════════════════
# VIDEO MOOD CLASSIFIER
# Takes a YouTube transcript + title → classifies mood/genre →
# returns a timed __DIRECTOR__ animation sequence for Marin to perform
# while the video plays.
# ═══════════════════════════════════════════════════════════════════════════════

# Mood keyword banks
_VIDEO_MOOD_KEYWORDS = {
    "sad": [
        "miss you", "goodbye", "crying", "tears", "heartbreak", "alone", "lost",
        "pain", "hurt", "grief", "sorrow", "broken", "farewell", "lonely",
        "remember", "gone", "never come back", "rain", "darkness", "empty",
        "last time", "dying", "sorry", "forgive", "mourn",
    ],
    "emotional": [
        "love", "feel", "soul", "emotion", "beautiful", "touch my heart",
        "inspire", "powerful", "story", "journey", "believe", "hope",
        "dream", "together", "forever", "promise", "life", "moment",
        "meaningful", "deep", "connection", "vulnerable",
    ],
    "hype": [
        "fire", "lit", "hype", "bass", "drop", "beat", "banger", "energy",
        "party", "jump", "crowd", "turn up", "loud", "hard", "trap",
        "drill", "bounce", "club", "night", "wild", "go crazy",
        "100", "skrrt", "yeah", "aye", "let's go",
    ],
    "chill": [
        "lofi", "lo-fi", "chill", "relax", "study", "calm", "smooth",
        "vibe", "mellow", "soft", "gentle", "ambient", "peaceful",
        "rain sounds", "coffee", "night", "slow", "cozy", "sleepy",
    ],
    "dance": [
        "dance", "dancing", "disco", "groove", "rhythm", "move",
        "floor", "spin", "shake", "funk", "choreography", "tiktok",
        "rumba", "salsa", "k-pop", "kpop", "hip hop",
    ],
    "hype_metal": [
        "metal", "scream", "rage", "destroy", "shred", "guitar", "riff",
        "breakdown", "mosh", "heavy", "brutal", "intense", "distortion",
    ],
}

# Mood → timed animation sequences
# Each entry: (t_offset_seconds, animation_name)
_VIDEO_MOOD_SEQUENCES = {
    "sad": [
        (0.0,  "sit_idle"),
        (25.0, "sadness"),
        (50.0, "caring"),
        (75.0, "neutral_idle"),
    ],
    "emotional": [
        (0.0,  "sit_idle"),
        (20.0, "caring"),
        (45.0, "neutral_idle2"),
        (70.0, "admiration"),
        (95.0, "neutral_idle"),
    ],
    "hype": [
        (0.0,  "excitement"),
        (15.0, "joy"),
        (30.0, "dance_1"),
        (45.0, "excitement2"),
        (60.0, "dance_2"),
        (75.0, "joy"),
    ],
    "chill": [
        (0.0,  "sit_idle"),
        (20.0, "neutral_idle"),
        (45.0, "sit_idle2"),
        (70.0, "neutral_idle2"),
        (95.0, "sit_idle"),
    ],
    "dance": [
        (0.0,  "dance_1"),
        (12.0, "dance_2"),
        (24.0, "dance_rumba"),
        (36.0, "dance_marachinostep"),
        (48.0, "dance_northern_soul_spin"),
        (60.0, "dance_1"),
        (72.0, "dance_2"),
    ],
    "hype_metal": [
        (0.0,  "excitement"),
        (12.0, "anger"),
        (24.0, "excitement2"),
        (36.0, "dance_1"),
        (48.0, "joy"),
        (60.0, "excitement"),
    ],
    "normal": [
        (0.0,  "sit_idle"),
        (30.0, "neutral_idle"),
        (60.0, "approval"),
        (90.0, "neutral_idle2"),
        (120.0, "sit_idle"),
    ],
}


def classify_video_mood(transcript: str, title: str = "") -> str:
    """
    Classify the mood of a YouTube video from its transcript + title.
    Returns one of: sad | emotional | hype | chill | dance | hype_metal | normal
    """
    text = (title + " " + (transcript or "")).lower()
    scores: dict[str, int] = dict.fromkeys(_VIDEO_MOOD_KEYWORDS, 0)

    for mood, keywords in _VIDEO_MOOD_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[mood] += 1

    best = max(scores, key=lambda k: scores[k])
    # Require at least 1 match, else fall back to normal
    if scores[best] == 0:
        return "normal"
    return best


def make_video_director_script(
    video_id: str,
    transcript: str = "",
    title: str = "",
    allow_dance: bool = False,
) -> tuple:
    """
    Build a timed __DIRECTOR__ tag for a YouTube video.
    allow_dance: only append __DANCE__ when user explicitly asked to dance.
    Returns (tag_string, mood).
    """
    mood = classify_video_mood(transcript, title)
    sequence = _VIDEO_MOOD_SEQUENCES.get(mood, _VIDEO_MOOD_SEQUENCES["normal"])

    script = []
    for t, anim in sequence:
        script.append({"t": t, "type": "anim", "value": anim, "dur": 12.0})
        script.append({"t": t, "type": "expr", "value": "relaxed", "dur": 10.0})

    encoded = encode_director_script(script)
    tag = f"__DIRECTOR__{encoded}"
    if allow_dance and mood in ("dance", "hype", "hype_metal"):
        tag += "__DANCE__"
    return tag, mood
