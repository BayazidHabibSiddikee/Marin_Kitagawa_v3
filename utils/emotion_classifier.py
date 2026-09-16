#!/usr/bin/env python3
"""
emotion_classifier.py — Hybrid emotion detection for Marin.

Combines:
  1. j-hartmann/emotion-english-distilroberta-base (transformer, 7 emotions, ~82MB)
  2. Keyword-boost layer that amplifies confident detections

The transformer loads lazily on first call in a background thread — zero startup delay.
If unavailable (no internet / transformers not installed), falls back to keyword-only.

Output maps directly to VRM expressions, physics emotions, and animations.
"""
import threading
from typing import Optional

# ── Label definitions ────────────────────────────────────────────────────────
EMOTION_LABELS = ["anger", "disgust", "fear", "joy", "neutral", "sadness", "surprise"]

# Maps transformer labels → Marin's VRM/physics/animation system
LABEL_TO_VRM: dict[str, dict[str, str]] = {
    "joy":      {"expr": "happy",     "phys": "joy",       "anim": "excitement"},
    "sadness":  {"expr": "sad",       "phys": "sad",       "anim": "sadness"},
    "anger":    {"expr": "angry",     "phys": "angry",     "anim": "neutral2"},
    "fear":     {"expr": "surprised", "phys": "surprised", "anim": "surprise"},
    "surprise": {"expr": "surprised", "phys": "surprised", "anim": "surprise"},
    "disgust":  {"expr": "angry",     "phys": "annoyed",   "anim": "neutral2"},
    "neutral":  {"expr": "neutral",   "phys": "neutral",   "anim": "neutral_idle"},
}

# Keyword boosts — when these words are present, amplify the matching emotion score.
# Each hit adds 0.12× to the label's score (capped at 1.4× total boost).
KEYWORD_BOOSTS: dict[str, list[str]] = {
    "joy":      ["haha", "lol", "lmao", "rofl", "hehe", "funny", "hilarious",
                 "amazing", "awesome", "incredible", "yay", "love", "❤", "💕",
                 "great", "happy", "wonderful", "perfect", "beautiful", "exciting"],
    "sadness":  ["sad", "sorry", "miss", "unfortunate", "hurt", "lost", "😢", "😭",
                 "broken", "alone", "crying", "tear", "grief", "mourning", "painful"],
    "anger":    ["ugh", "argh", "angry", "hate", "frustrated", "stop", "seriously",
                 "annoyed", "furious", "rage", "terrible", "stupid", "idiot"],
    "fear":     ["scared", "afraid", "terrified", "worried", "anxious", "nervous",
                 "frightened", "panic", "danger", "threat", "risk"],
    "surprise": ["wow", "whoa", "really?", "omg", "no way", "what?!", "unbelievable",
                 "shocking", "unexpected", "wait", "seriously?", "incredible"],
    "disgust":  ["gross", "disgusting", "eww", "ugh", "awful", "terrible",
                 "horrible", "nasty", "revolting", "yuck"],
    "neutral":  [],
}

# ── Lazy model loader ─────────────────────────────────────────────────────────
_clf = None
_clf_lock = threading.Lock()
_clf_loading = False
MODEL_NAME = "j-hartmann/emotion-english-distilroberta-base"


def _get_classifier():
    """Return the HuggingFace pipeline, or the string 'unavailable' on failure."""
    global _clf, _clf_loading
    if _clf is not None:
        return _clf
    with _clf_lock:
        if _clf is not None:
            return _clf
        try:
            from transformers import pipeline
            print(f"[EmotionCLF] Loading {MODEL_NAME} …")
            _clf = pipeline(
                "text-classification",
                model=MODEL_NAME,
                top_k=None,        # return all 7 label scores
                device=-1,         # CPU — no GPU needed
                truncation=True,
                max_length=512,
            )
            print("[EmotionCLF] Model loaded ✓")
        except Exception as e:
            print(f"[EmotionCLF] Could not load transformer: {e}  → keyword-only mode")
            _clf = "unavailable"
    return _clf


# ── Core API ──────────────────────────────────────────────────────────────────

def classify_emotion(text: str, min_confidence: float = 0.28) -> dict:
    """
    Classify the dominant emotion in *text* using transformer + keyword hybrid.

    Args:
        text:           Input text (up to 512 chars is used).
        min_confidence: Minimum score for a non-neutral result.

    Returns:
        {
            "emotion":    str,          # top label
            "confidence": float,        # 0..1 after keyword boosting
            "expr":       str,          # VRM expression key
            "phys":       str,          # physics emotion name
            "anim":       str,          # animation name
            "all_scores": dict[str,float],
        }
    """
    if not text or not text.strip():
        return _neutral(all_scores=None)

    clf = _get_classifier()
    raw_scores: dict[str, float] = {}

    # ── Transformer pass ─────────────────────────────────────────────────────
    if clf and clf != "unavailable":
        try:
            # pipeline returns [ [{"label":…, "score":…}, …] ]
            results = clf(text[:512])
            for item in results[0]:
                raw_scores[item["label"]] = float(item["score"])
        except Exception as e:
            print(f"[EmotionCLF] Inference error: {e}")

    # ── Keyword-only fallback ─────────────────────────────────────────────────
    if not raw_scores:
        raw_scores = _keyword_fallback(text)

    # ── Keyword boost layer ───────────────────────────────────────────────────
    boosted: dict[str, float] = {}
    for label, score in raw_scores.items():
        boost = _keyword_boost(text, label)
        boosted[label] = score * boost

    # Renormalise so all scores sum to 1.0
    total = sum(boosted.values())
    if total > 0:
        boosted = {k: v / total for k, v in boosted.items()}

    # ── Pick top label ────────────────────────────────────────────────────────
    top_label = max(boosted, key=lambda k: boosted[k])
    top_score = boosted[top_label]

    if top_score < min_confidence or top_label == "neutral":
        return _neutral(all_scores=boosted)

    mapping = LABEL_TO_VRM.get(top_label, LABEL_TO_VRM["neutral"])
    return {
        "emotion":    top_label,
        "confidence": round(top_score, 3),
        "expr":       mapping["expr"],
        "phys":       mapping["phys"],
        "anim":       mapping["anim"],
        "all_scores": {k: round(v, 3) for k, v in boosted.items()},
    }


def classify_emotion_fast(text: str) -> dict:
    """
    Keyword-only classification (no transformer, always instant).
    Used for real-time streaming chunks where latency matters.
    """
    raw_scores = _keyword_fallback(text)
    top_label  = max(raw_scores, key=lambda k: raw_scores[k])
    top_score  = raw_scores[top_label]
    if top_score < 0.30 or top_label == "neutral":
        return _neutral()
    mapping = LABEL_TO_VRM.get(top_label, LABEL_TO_VRM["neutral"])
    return {
        "emotion":    top_label,
        "confidence": round(top_score, 3),
        "expr":       mapping["expr"],
        "phys":       mapping["phys"],
        "anim":       mapping["anim"],
        "all_scores": {k: round(v, 3) for k, v in raw_scores.items()},
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _keyword_boost(text: str, label: str) -> float:
    """Return a multiplier [1.0 .. 1.4] based on keyword hit count."""
    lower    = text.lower()
    keywords = KEYWORD_BOOSTS.get(label, [])
    hits     = sum(1 for kw in keywords if kw in lower)
    return 1.0 + min(hits * 0.12, 0.4)


def _keyword_fallback(text: str) -> dict[str, float]:
    """Keyword-based scoring when the transformer is unavailable."""
    lower  = text.lower()
    scores = {label: 0.0 for label in EMOTION_LABELS}
    for label, keywords in KEYWORD_BOOSTS.items():
        hits = sum(1 for kw in keywords if kw in lower)
        scores[label] = hits * 0.18
    # Ensure neutral is at least 0.1 so the dict always has a winner
    scores["neutral"] = max(0.1, scores.get("neutral", 0.1))
    total = sum(scores.values())
    if total > 0:
        scores = {k: v / total for k, v in scores.items()}
    return scores


def _neutral(all_scores: Optional[dict] = None) -> dict:
    return {
        "emotion":    "neutral",
        "confidence": 1.0,
        "expr":       "neutral",
        "phys":       "neutral",
        "anim":       "neutral_idle",
        "all_scores": all_scores or {"neutral": 1.0},
    }


# ── Background preload ────────────────────────────────────────────────────────
# Starts downloading the model in the background immediately on import,
# so the first real classify_emotion() call is instant.
def _preload():
    try:
        _get_classifier()
    except Exception:
        pass

threading.Thread(target=_preload, daemon=True, name="EmotionCLF-preload").start()
