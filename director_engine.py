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

import re
import json
import base64
from typing import List, Dict, Any

# ── Emotion → Animation + Expression mappings ──────────────────────────────

_EMOTION_MAP = {
    # happy family
    "happy":      {"anim": "joy",         "expr": "happy"},
    "excited":    {"anim": "excitement",  "expr": "happy"},
    "joy":        {"anim": "joy2",        "expr": "happy"},
    "laugh":      {"anim": "amusement",   "expr": "happy"},
    "proud":      {"anim": "pride",       "expr": "happy"},
    "love":       {"anim": "love",        "expr": "happy"},
    # neutral / thinking
    "neutral":    {"anim": "neutral_idle", "expr": "neutral"},
    "thinking":   {"anim": "curiosity",   "expr": "thinking"},
    "curious":    {"anim": "curiosity2",  "expr": "thinking"},
    "explaining": {"anim": "neutral2",    "expr": "neutral"},
    "confident":  {"anim": "pride2",      "expr": "neutral"},
    # surprise / realisation
    "surprise":   {"anim": "surprise",    "expr": "surprised"},
    "realization":{"anim": "realization", "expr": "surprised"},
    "shock":      {"anim": "surprise2",   "expr": "surprised"},
    # sadness / empathy
    "sad":        {"anim": "sadness",     "expr": "sad"},
    "grief":      {"anim": "grief",       "expr": "sad"},
    "remorse":    {"anim": "remorse",     "expr": "sad"},
    # anger / frustration
    "angry":      {"anim": "anger",       "expr": "angry"},
    "annoyed":    {"anim": "annoyance",   "expr": "angry"},
    "disgust":    {"anim": "disgust",     "expr": "angry"},
    # admiration / caring
    "admire":     {"anim": "admiration",  "expr": "happy"},
    "caring":     {"anim": "caring",      "expr": "happy"},
    "gratitude":  {"anim": "gratitude",   "expr": "happy"},
    # other
    "embarrassed":{"anim": "embarrassment","expr":"neutral"},
    "nervous":    {"anim": "nervousness", "expr": "neutral"},
    "fear":       {"anim": "fear",        "expr": "surprised"},
    "dancing":    {"anim": "dance_1",     "expr": "happy"},
    "greeting":   {"anim": "action_greeting","expr":"happy"},
}

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

def _detect_sentence_emotion(sentence: str) -> str:
    lower = sentence.lower()
    scores: Dict[str, int] = {}
    for emotion, keywords in _EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                scores[emotion] = scores.get(emotion, 0) + 1
    if not scores:
        return "neutral"
    return max(scores, key=lambda k: scores[k])


# ── Text segmentation ───────────────────────────────────────────────────────

def _split_into_segments(text: str) -> List[str]:
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

def build_director_script(response_text: str, base_emotion: str = "neutral") -> List[Dict[str, Any]]:
    """
    Parse Marin's full response and produce a timed action script.

    Returns a list of action dicts sorted by 't' (time offset in seconds).
    Each action:
        { "t": float, "type": str, "value": str, "dur": float }
    """
    segments = _split_into_segments(response_text)
    script: List[Dict[str, Any]] = []
    cursor = 0.0  # current time cursor

    # Opening action — play the base emotion animation immediately
    base = _EMOTION_MAP.get(base_emotion, _EMOTION_MAP["neutral"])
    script.append({"t": 0.0, "type": "anim",  "value": base["anim"], "dur": 1.5})
    script.append({"t": 0.0, "type": "expr",  "value": base["expr"], "dur": 1.0})

    prev_emotion = base_emotion

    for i, seg in enumerate(segments):
        emotion = _detect_sentence_emotion(seg)
        dur = _estimate_duration(seg)

        # Add a small gap before the first segment
        t_start = cursor if i == 0 else cursor + 0.1

        # Emit a talk segment (lipsync text chunk timing)
        script.append({"t": t_start, "type": "talk", "value": seg, "dur": dur})

        # Emit animation/expression change when emotion shifts
        if emotion != prev_emotion and emotion != "neutral":
            mapping = _EMOTION_MAP.get(emotion, _EMOTION_MAP["neutral"])
            script.append({"t": t_start,       "type": "anim", "value": mapping["anim"], "dur": dur})
            script.append({"t": t_start + 0.1, "type": "expr", "value": mapping["expr"], "dur": dur})
            prev_emotion = emotion

        # For long pauses between sentences, add a brief idle
        if i < len(segments) - 1:
            cursor = t_start + dur + 0.15
        else:
            cursor = t_start + dur

    # Return-to-idle at end
    script.append({"t": cursor + 0.5, "type": "anim",  "value": "neutral_idle", "dur": 99.0})
    script.append({"t": cursor + 0.5, "type": "expr",  "value": "neutral",      "dur": 99.0})

    # Sort by time
    script.sort(key=lambda a: a["t"])
    return script


# ── Encoding ────────────────────────────────────────────────────────────────

def encode_director_script(script: List[Dict[str, Any]]) -> str:
    """Encode the script as a base64 string for safe stream embedding."""
    raw = json.dumps(script, separators=(',', ':'))
    return base64.b64encode(raw.encode()).decode()


def decode_director_script(encoded: str) -> List[Dict[str, Any]]:
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
        (0.0,  "sadness"),
        (8.0,  "remorse"),
        (18.0, "grief"),
        (30.0, "sadness2"),
        (42.0, "neutral_idle"),
        (55.0, "remorse2"),
        (70.0, "sadness"),
        (85.0, "neutral_idle"),
    ],
    "emotional": [
        (0.0,  "caring"),
        (10.0, "love"),
        (22.0, "admiration"),
        (35.0, "neutral_idle2"),
        (48.0, "caring1"),
        (62.0, "love3"),
        (78.0, "neutral_idle"),
    ],
    "hype": [
        (0.0,  "dance_1"),
        (8.0,  "dance_dab"),
        (16.0, "excitement"),
        (24.0, "dance_2"),
        (32.0, "dance_pushback"),
        (40.0, "joy"),
        (48.0, "dance_gangnam_style"),
        (58.0, "dance_northern_soul_spin"),
        (68.0, "excitement2"),
        (76.0, "dance_1"),
    ],
    "chill": [
        (0.0,  "neutral_idle"),
        (12.0, "sit_idle"),
        (28.0, "neutral_idle2"),
        (45.0, "sit_idle2"),
        (62.0, "neutral4"),
        (80.0, "neutral_idle"),
    ],
    "dance": [
        (0.0,  "dance_rumba"),
        (9.0,  "dance_marachinostep"),
        (18.0, "dance_headdrop"),
        (27.0, "dance_ontop"),
        (36.0, "dance_backup"),
        (45.0, "dance_northern_soul_spin"),
        (54.0, "dance_gangnam_style"),
        (63.0, "dance_1"),
        (72.0, "dance_2"),
        (81.0, "dance_rumba"),
    ],
    "hype_metal": [
        (0.0,  "excitement"),
        (7.0,  "anger"),
        (14.0, "dance_1"),
        (21.0, "excitement3"),
        (28.0, "anger2"),
        (35.0, "dance_2"),
        (42.0, "joy"),
        (50.0, "excitement2"),
        (58.0, "dance_dab"),
    ],
    "normal": [
        (0.0,  "neutral_idle"),
        (15.0, "curiosity"),
        (32.0, "neutral2"),
        (50.0, "neutral_idle2"),
        (68.0, "curiosity2"),
        (85.0, "neutral_idle"),
    ],
}


def classify_video_mood(transcript: str, title: str = "") -> str:
    """
    Classify the mood of a YouTube video from its transcript + title.
    Returns one of: sad | emotional | hype | chill | dance | hype_metal | normal
    """
    text = (title + " " + (transcript or "")).lower()
    scores: dict[str, int] = {mood: 0 for mood in _VIDEO_MOOD_KEYWORDS}

    for mood, keywords in _VIDEO_MOOD_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[mood] += 1

    best = max(scores, key=lambda k: scores[k])
    # Require at least 1 match, else fall back to normal
    if scores[best] == 0:
        return "normal"
    return best


def make_video_director_script(video_id: str, transcript: str = "", title: str = "") -> str:
    """
    Build a timed __DIRECTOR__ tag for a YouTube video.
    Marin performs mood-matched animations while the video plays.
    Returns the full __DIRECTOR__<base64> stream tag.
    """
    mood = classify_video_mood(transcript, title)
    sequence = _VIDEO_MOOD_SEQUENCES.get(mood, _VIDEO_MOOD_SEQUENCES["normal"])

    script = []
    for t, anim in sequence:
        script.append({"t": t, "type": "anim", "value": anim, "dur": 8.0})

    # Add __DANCE__ flag for dance/hype moods so frontend knows to loop
    is_dance_mood = mood in ("dance", "hype", "hype_metal")

    encoded = encode_director_script(script)
    tag = f"__DIRECTOR__{encoded}"
    if is_dance_mood:
        tag += "__DANCE__"
    return tag, mood
