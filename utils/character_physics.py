#!/usr/bin/env python3
"""
character_physics.py — Soft-body physics + emotion-driven body parameters for Marin's VRM avatar.

Features:
  • Spring-damper pendulum simulation for hair, chest, and spine sway
  • Emotion → physics parameter map (stiffness/damping/amplitude per emotion)
  • Lexical emotion detection from text chunks (mirrors liveDirectorScan)
  • REST endpoint: GET /api/physics/emotion?text=… returns physics params + detected emotion

All physics are mass-spring-damper systems:
    F = -k * displacement - c * velocity + gravity_component
Where k = spring stiffness, c = damping coefficient.
"""

import math
from dataclasses import dataclass, field, asdict
from typing import Optional


# ── EMOTION → PHYSICS PARAMETER MAP ───────────────────────────────────────────
# Each emotion shifts spring stiffness, damping, and rest-posture offsets.
# These values were tuned by observation of real body language patterns.

EMOTION_PHYSICS = {
    "neutral": {
        "hair_k": 0.0016,      # spring stiffness (N/m, normalized)
        "hair_c": 0.06,        # damping ratio
        "hair_amp": 0.02,      # idle amplitude (m)
        "spine_k": 0.002,
        "spine_c": 0.08,
        "spine_amp": 0.005,
        "chest_k": 0.001,
        "chest_c": 0.05,
        "chest_amp": 0.003,
        "head_tilt": 0.0,
        "shoulder_drop": 0.0,
    },
    "joy": {
        "hair_k": 0.0012,
        "hair_c": 0.04,
        "hair_amp": 0.08,      # bouncy when happy
        "spine_k": 0.0015,
        "spine_c": 0.05,
        "spine_amp": 0.015,
        "chest_k": 0.0008,
        "chest_c": 0.04,
        "chest_amp": 0.01,
        "head_tilt": 0.05,
        "shoulder_drop": -0.02,  # shoulders lift when happy
    },
    "excited": {
        "hair_k": 0.0008,
        "hair_c": 0.03,
        "hair_amp": 0.15,      # lots of bounce
        "spine_k": 0.001,
        "spine_c": 0.04,
        "spine_amp": 0.03,
        "chest_k": 0.0006,
        "chest_c": 0.03,
        "chest_amp": 0.02,
        "head_tilt": 0.08,
        "shoulder_drop": -0.04,
    },
    "sad": {
        "hair_k": 0.0025,
        "hair_c": 0.12,
        "hair_amp": 0.01,      # heavy, slow, little movement
        "spine_k": 0.003,
        "spine_c": 0.15,
        "spine_amp": -0.02,    # slumped forward
        "chest_k": 0.0015,
        "chest_c": 0.1,
        "chest_amp": -0.01,    # chest collapsed
        "head_tilt": -0.08,    # head down
        "shoulder_drop": 0.04,
    },
    "angry": {
        "hair_k": 0.003,
        "hair_c": 0.1,
        "hair_amp": 0.03,
        "spine_k": 0.004,
        "spine_c": 0.12,
        "spine_amp": 0.01,     # tense, leaning forward slightly
        "chest_k": 0.002,
        "chest_c": 0.08,
        "chest_amp": 0.015,    # chest puffed
        "head_tilt": 0.02,
        "shoulder_drop": -0.05,  # shoulders raised (tense)
    },
    "thinking": {
        "hair_k": 0.002,
        "hair_c": 0.07,
        "hair_amp": 0.01,
        "spine_k": 0.0025,
        "spine_c": 0.09,
        "spine_amp": 0.005,
        "chest_k": 0.0012,
        "chest_c": 0.06,
        "chest_amp": 0.004,
        "head_tilt": 0.1,     # tilted — looking up/away
        "shoulder_drop": 0.0,
    },
    "surprised": {
        "hair_k": 0.0005,
        "hair_c": 0.02,
        "hair_amp": 0.2,      # sudden jump
        "spine_k": 0.0008,
        "spine_c": 0.03,
        "spine_amp": 0.04,
        "chest_k": 0.0005,
        "chest_c": 0.02,
        "chest_amp": 0.03,
        "head_tilt": -0.05,   # head back
        "shoulder_drop": -0.06,
    },
    "fear": {
        "hair_k": 0.0035,
        "hair_c": 0.14,
        "hair_amp": 0.02,
        "spine_k": 0.004,
        "spine_c": 0.15,
        "spine_amp": -0.015,   # hunched
        "chest_k": 0.002,
        "chest_c": 0.1,
        "chest_amp": -0.01,
        "head_tilt": -0.06,
        "shoulder_drop": 0.06,
    },
    "love": {
        "hair_k": 0.001,
        "hair_c": 0.035,
        "hair_amp": 0.06,
        "spine_k": 0.0012,
        "spine_c": 0.045,
        "spine_amp": 0.01,
        "chest_k": 0.0007,
        "chest_c": 0.035,
        "chest_amp": 0.008,
        "head_tilt": 0.06,
        "shoulder_drop": -0.01,
    },
    "confident": {
        "hair_k": 0.0014,
        "hair_c": 0.05,
        "hair_amp": 0.04,
        "spine_k": 0.0018,
        "spine_c": 0.06,
        "spine_amp": 0.01,
        "chest_k": 0.0009,
        "chest_c": 0.04,
        "chest_amp": 0.012,
        "head_tilt": 0.0,
        "shoulder_drop": -0.03,
    },
}

DEFAULT_PHYSICS = EMOTION_PHYSICS["neutral"]


# ── LEXICAL CUES FOR EMOTION DETECTION ────────────────────────────────────────
_EMOTION_CUES = {
    "joy":      ["happy", "great", "wonderful", "awesome", "amazing", "love it", "❤", "😊", "🎉"],
    "excited":  ["wow", "omg", "incredible", "yes!", "yay", "!!!", "🥳", "can't wait", "thrilled"],
    "sad":      ["sorry", "sad", "unfortunately", "miss", "😢", "😭", "regret", "disappointed"],
    "angry":    ["angry", "frustrated", "terrible", "hate", "annoyed", "ridiculous", "😠", "😡"],
    "thinking": ["hmm", "let me think", "analyze", "consider", "perhaps", "maybe", "figure out", "🤔"],
    "surprised":["whoa", "no way", "really?", "shocked", "😮", "🤯", "wait", "seriously?"],
    "fear":     ["scared", "afraid", "worried", "anxious", "nervous", "😰", "🫣", "terrified"],
    "love":     ["love you", "adore", "sweetheart", "💕", "💋", "😘", "❤️", "affectionate", "kiss"],
    "confident":["i can", "strong", "ready", "success", "win", "trust me", "got this", "💪"],
}


def classify_emotion(text: str) -> tuple[str, float]:
    """Return (emotion_name, confidence 0..1) from text. Neutral on tie."""
    lower = text.lower()
    scores: dict[str, float] = {}
    for emotion, cues in _EMOTION_CUES.items():
        score = 0.0
        for cue in cues:
            if cue in lower:
                score += 1.0
        if score > 0:
            scores[emotion] = score

    if not scores:
        return "neutral", 0.0

    max_emotion = max(scores, key=scores.get)
    total = sum(scores.values())
    confidence = min(1.0, scores[max_emotion] / max(total, 1.0))
    return max_emotion, confidence


def get_emotion_params(emotion: str) -> dict:
    """Return physics parameters for an emotion; falls back to neutral."""
    return EMOTION_PHYSICS.get(emotion, DEFAULT_PHYSICS)


# ── SPRING DAMPER PHYSICS SIMULATOR ───────────────────────────────────────────

@dataclass
class Spring:
    """Single-degree-of-freedom mass-spring-damper system."""
    k: float = 0.0016    # stiffness
    c: float = 0.06      # damping
    mass: float = 1.0
    displacement: float = 0.0
    velocity: float = 0.0
    target: float = 0.0  # driven displacement (for animation)
    idle_amplitude: float = 0.0
    freq_hz: float = 2.0  # idle oscillation frequency

    def step(self, dt: float, external_force: float = 0.0) -> float:
        """Integrate one frame. Returns current displacement."""
        # Spring force toward target
        spring_f = -self.k * (self.displacement - self.target)
        # Damping force
        damp_f = -self.c * self.velocity
        # Total acceleration
        accel = (spring_f + damp_f + external_force) / self.mass
        # Semi-implicit Euler integration
        self.velocity += accel * dt
        self.displacement += self.velocity * dt
        return self.displacement

    def add_idle_oscillation(self, t: float) -> float:
        """Add sinusoidal idle oscillation for natural breathing/movement."""
        return self.idle_amplitude * math.sin(2 * math.pi * self.freq_hz * t)


@dataclass
class BodyPhysics:
    """Full soft-body physics state for Marin's avatar."""
    hair: Spring = field(default_factory=lambda: Spring(k=0.0016, c=0.06, idle_amplitude=0.02, freq_hz=1.8))
    spine: Spring = field(default_factory=lambda: Spring(k=0.002, c=0.08, idle_amplitude=0.005, freq_hz=1.2))
    chest: Spring = field(default_factory=lambda: Spring(k=0.001, c=0.05, idle_amplitude=0.003, freq_hz=1.5))
    head_tilt: float = 0.0
    shoulder_drop: float = 0.0

    current_emotion: str = "neutral"
    transition_progress: float = 1.0  # 0 = old params, 1 = new params

    def apply_emotion(self, emotion: str) -> None:
        """Smoothly transition physics parameters to match an emotion."""
        if emotion == self.current_emotion:
            return
        prev = EMOTION_PHYSICS.get(self.current_emotion, DEFAULT_PHYSICS)
        curr = EMOTION_PHYSICS.get(emotion, DEFAULT_PHYSICS)
        self.current_emotion = emotion
        # Interpolate springs
        self._interp(prev, curr, 0.0)
        self.transition_progress = 0.0

    def _interp(self, a: dict, b: dict, t: float) -> None:
        """Lerp between two param dicts, applied to springs."""
        def lerp(spring_key, prop, scale=1.0):
            va = a.get(f"{spring_key}_{prop}", 0)
            vb = b.get(f"{spring_key}_{prop}", 0)
            setattr(getattr(self, spring_key), prop, va + (vb - va) * t * scale)

        lerp("hair", "k")
        lerp("hair", "c")
        lerp("hair", "idle_amplitude")
        lerp("spine", "k")
        lerp("spine", "c")
        lerp("spine", "idle_amplitude")
        lerp("chest", "k")
        lerp("chest", "c")
        lerp("chest", "idle_amplitude")
        self.head_tilt = a.get("head_tilt", 0) + (b.get("head_tilt", 0) - a.get("head_tilt", 0)) * t
        self.shoulder_drop = a.get("shoulder_drop", 0) + (b.get("shoulder_drop", 0) - a.get("shoulder_drop", 0)) * t

    def step(self, dt: float, elapsed: float) -> dict:
        """Advance physics one frame. Returns blendshape-style output dict."""
        # Ease transition over ~0.5s
        if self.transition_progress < 1.0:
            self.transition_progress = min(1.0, self.transition_progress + dt / 0.5)
            t = self.transition_progress
            prev = EMOTION_PHYSICS.get(
                [k for k, v in EMOTION_PHYSICS.items() if v is not None][
                    list(EMOTION_PHYSICS.keys()).index(self.current_emotion)
                ] if False else "neutral", DEFAULT_PHYSICS
            )
            curr = EMOTION_PHYSICS.get(self.current_emotion, DEFAULT_PHYSICS)
            self._interp(prev if prev is not EMOTION_PHYSICS[self.current_emotion] else curr, curr, t)

        # Add idle breathing to target
        breath = math.sin(2 * math.pi * 1.5 * elapsed) * 0.003
        self.chest.target = breath

        # Step springs
        hair_disp = self.hair.step(dt) + self.hair.add_idle_oscillation(elapsed)
        spine_disp = self.spine.step(dt) + self.spine.add_idle_oscillation(elapsed)
        chest_disp = self.chest.step(dt)

        return {
            "emotion": self.current_emotion,
            "transition": round(self.transition_progress, 3),
            "hair_offset_x": round(hair_disp * 0.02, 4),
            "hair_offset_y": round(hair_disp * 0.005, 4),
            "hair_sway": round(math.sin(elapsed * 3.14) * self.hair.idle_amplitude, 4),
            "spine_forward": round(spine_disp * 0.01, 4),
            "spine_tilt": round(math.sin(elapsed * 2.1) * self.spine.idle_amplitude * 0.5, 4),
            "chest_expand": round(chest_disp * 0.005, 4),
            "head_tilt": round(self.head_tilt, 4),
            "shoulder_drop": round(self.shoulder_drop, 4),
        }

    def to_dict(self) -> dict:
        """Return current state as JSON-serializable dict."""
        curr = EMOTION_PHYSICS.get(self.current_emotion, DEFAULT_PHYSICS)
        return {
            "emotion": self.current_emotion,
            "stiffness_hair": round(curr["hair_k"], 4),
            "damping_hair": round(curr["hair_c"], 4),
            "stiffness_spine": round(curr["spine_k"], 4),
            "damping_spine": round(curr["spine_c"], 4),
            "head_tilt": round(curr["head_tilt"], 4),
            "shoulder_drop": round(curr["shoulder_drop"], 4),
        }


# ── PUBLIC API ─────────────────────────────────────────────────────────────────

_state = BodyPhysics()


def analyze_text(text: str) -> dict:
    """Classify emotion from text and return physics parameters + detection result."""
    emotion, confidence = classify_emotion(text)
    params = get_emotion_params(emotion)
    params["detected_emotion"] = emotion
    params["confidence"] = round(confidence, 3)
    return params


def get_current_state() -> dict:
    """Return current physics state (for hot-reload or sync)."""
    return _state.to_dict()


def apply_emotion_from_text(text: str) -> dict:
    """Analyze text, update physics state, return both classification and current params."""
    emotion, confidence = classify_emotion(text)
    _state.apply_emotion(emotion)
    return {
        "emotion": emotion,
        "confidence": round(confidence, 3),
        "params": _state.to_dict(),
    }
