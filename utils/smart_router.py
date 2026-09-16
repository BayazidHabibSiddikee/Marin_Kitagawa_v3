#!/usr/bin/env python3
"""
smart_router.py — FreeLLMAPI-inspired bandit router for Marin's LLM providers.

Ported from /home/sword/freellmapi/server/src/services/router.ts + scoring.ts

Key algorithms:
  • Beta-posterior Thompson sampling for reliability (α successes + 1, β failures + 1)
  • Convex combination score: w_rel·reliability + w_speed·speed + w_intel·intelligence
  • Time-decayed 429 penalties (3pts per hit, cap 10, decay 1pt / 2min)
  • 3-consecutive 5xx → skip provider for 2 minutes
  • Round-robin within equal-score tier (prevents hot-spotting)
  • Strategy presets: balanced / smartest / fastest / reliable

Usage in llm_manager.py:
    from utils.smart_router import get_router, RoutingStrategy

    router = get_router()
    router.register_provider("openrouter", intelligence=0.8, priority=0)
    router.register_provider("groq",        intelligence=0.65, priority=1)

    best = router.pick_provider(candidates=["openrouter", "groq"])
    # ... call LLM ...
    router.record_success(best, latency_ms=340, tokens_per_sec=52)
    # on 429:  router.record_rate_limit(best)
    # on 5xx:  router.record_failure(best)
"""

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

# ── Strategy presets (same as freellmapi BANDIT_PRESETS) ──────────────────────
RoutingStrategy = Literal["priority", "balanced", "smartest", "fastest", "reliable"]

BANDIT_PRESETS: dict[str, dict[str, float]] = {
    # Reliability leads; speed and intelligence split the rest evenly.
    "balanced":  {"reliability": 0.50, "speed": 0.25, "intelligence": 0.25},
    # Intelligence leads, but reliability still carries real weight.
    "smartest":  {"reliability": 0.35, "speed": 0.10, "intelligence": 0.55},
    # Speed leads; reliability keeps a fast-but-broken model from winning.
    "fastest":   {"reliability": 0.35, "speed": 0.55, "intelligence": 0.10},
    # Reliability dominates — for clients that just want it to work.
    "reliable":  {"reliability": 0.70, "speed": 0.15, "intelligence": 0.15},
}

# ── Tuning constants (from scoring.ts) ────────────────────────────────────────
PENALTY_PER_429   = 3          # each 429 adds this many priority positions
MAX_PENALTY       = 10         # cap so a model doesn't sink forever
DECAY_INTERVAL_S  = 120.0      # penalty decays every 2 minutes
DECAY_AMOUNT      = 1          # remove this much penalty per decay interval

SPEED_SCALE_TOK_S = 60.0       # tok/s at which throughput ≈ 0.63 (saturating)
TTFB_BEST_MS      = 300.0      # ≤ this → full latency credit
TTFB_WORST_MS     = 5000.0     # ≥ this → zero latency credit
THROUGHPUT_WEIGHT = 0.6        # within the speed axis
TTFB_WEIGHT       = 0.4

PRIOR_SUCCESS = 1.0            # Beta(1,1) = uniform prior — new model is uncertain
PRIOR_FAILURE = 1.0

HEALTH_SKIP_STRIKES = 3        # consecutive 5xx before skipping
HEALTH_SKIP_SECS    = 120.0    # skip duration in seconds


@dataclass
class _ProviderStats:
    provider_id:  str
    intelligence: float = 0.5   # 0..1, static capability score
    priority:     int   = 0     # lower = higher priority (fallback order)

    # Beta posterior counts (decay-weighted)
    successes: float = 0.0
    failures:  float = 0.0

    # Latency tracking
    total_latency_ms: float = 0.0
    latency_count:    int   = 0

    # Throughput tracking
    total_tps:  float = 0.0
    tps_count:  int   = 0

    # 429 tracking
    rate_limit_count:   int   = 0
    rate_limit_penalty: float = 0.0
    rate_limit_last:    float = 0.0   # monotonic timestamp

    # Health tracking
    consecutive_5xx:   int   = 0
    health_skip_until: float = 0.0   # monotonic timestamp

    # Round-robin within tier
    rr_counter: int = 0


class SmartRouter:
    """
    Thread-safe bandit router. One instance is shared via get_router().
    """

    def __init__(self, default_strategy: RoutingStrategy = "balanced"):
        self._stats: dict[str, _ProviderStats] = {}
        self._lock = threading.RLock()
        self._strategy: RoutingStrategy = default_strategy

    # ── Registration ──────────────────────────────────────────────────────────

    def register_provider(
        self,
        provider_id:   str,
        intelligence:  float = 0.5,
        priority:      int   = 0,
    ) -> None:
        """Register a provider if not already registered."""
        with self._lock:
            if provider_id not in self._stats:
                self._stats[provider_id] = _ProviderStats(
                    provider_id=provider_id,
                    intelligence=max(0.0, min(1.0, intelligence)),
                    priority=priority,
                )

    # ── Recording outcomes ────────────────────────────────────────────────────

    def record_success(
        self,
        provider_id:   str,
        latency_ms:    float = 500.0,
        tokens_per_sec: float = 30.0,
    ) -> None:
        """Record a successful LLM call."""
        with self._lock:
            s = self._ensure(provider_id)
            s.successes      += 1.0
            s.consecutive_5xx = 0
            s.health_skip_until = 0.0
            if latency_ms > 0:
                s.total_latency_ms += latency_ms
                s.latency_count    += 1
            if tokens_per_sec > 0:
                s.total_tps  += tokens_per_sec
                s.tps_count  += 1
            # Reduce existing penalty on success
            s.rate_limit_penalty = max(0.0, s.rate_limit_penalty - 1.0)

    def record_rate_limit(self, provider_id: str) -> None:
        """Record a 429 — penalty increases, provider sinks in ranking."""
        with self._lock:
            s = self._ensure(provider_id)
            now = time.monotonic()
            # Apply decay to existing penalty first
            if s.rate_limit_last > 0:
                elapsed    = now - s.rate_limit_last
                decay_steps = int(elapsed / DECAY_INTERVAL_S)
                s.rate_limit_penalty = max(0.0, s.rate_limit_penalty - decay_steps * DECAY_AMOUNT)
            s.rate_limit_count  += 1
            s.rate_limit_last    = now
            s.rate_limit_penalty = min(s.rate_limit_penalty + PENALTY_PER_429, MAX_PENALTY)
            s.failures          += 0.3  # soft failure — not as bad as 5xx

    def record_failure(self, provider_id: str) -> None:
        """Record a 5xx — 3 consecutive failures skips provider for 2 min."""
        with self._lock:
            s = self._ensure(provider_id)
            s.failures         += 1.0
            s.consecutive_5xx  += 1
            if s.consecutive_5xx >= HEALTH_SKIP_STRIKES:
                s.health_skip_until = time.monotonic() + HEALTH_SKIP_SECS

    def record_context_length_error(self, provider_id: str) -> None:
        """Context too long — soft failure, no penalty escalation."""
        with self._lock:
            s = self._ensure(provider_id)
            s.failures += 0.1  # barely counts against reliability

    # ── Routing ───────────────────────────────────────────────────────────────

    def pick_provider(
        self,
        candidates: Optional[list[str]] = None,
        strategy:   Optional[RoutingStrategy] = None,
    ) -> Optional[str]:
        """
        Select the best provider using bandit scoring.

        Args:
            candidates: subset of provider IDs to consider. None = all registered.
            strategy:   override the router's default strategy.

        Returns:
            provider_id or None if all candidates are unhealthy / unknown.
        """
        strat   = strategy or self._strategy
        weights = BANDIT_PRESETS.get(strat, BANDIT_PRESETS["balanced"])

        with self._lock:
            pool = list(candidates if candidates is not None else self._stats.keys())
            if not pool:
                return None

            now = time.monotonic()
            scored: list[tuple[float, int, str]] = []  # (score, rr, id)

            for pid in pool:
                s = self._stats.get(pid)
                if s is None:
                    # Unknown provider: give neutral exploratory score
                    scored.append((0.5, 0, pid))
                    continue

                # Skip providers in health cooldown
                if s.health_skip_until > now:
                    continue

                score = self._compute_score(s, weights, now)
                # Use priority as tiebreaker (lower priority number = earlier in order)
                scored.append((score, s.priority, pid))

            if not scored:
                return None

            # Sort: score DESC, then priority ASC (lower = better)
            scored.sort(key=lambda x: (-x[0], x[1]))
            return scored[0][2]

    def pick_ordered(
        self,
        candidates: Optional[list[str]] = None,
        strategy:   Optional[RoutingStrategy] = None,
    ) -> list[str]:
        """Return all candidates sorted best-first (for fallback chains)."""
        strat   = strategy or self._strategy
        weights = BANDIT_PRESETS.get(strat, BANDIT_PRESETS["balanced"])

        with self._lock:
            pool = list(candidates if candidates is not None else self._stats.keys())
            now  = time.monotonic()
            scored: list[tuple[float, int, str]] = []

            for pid in pool:
                s = self._stats.get(pid)
                skip = s.health_skip_until > now if s else False
                score = 0.0 if skip else (self._compute_score(s, weights, now) if s else 0.5)
                pri   = s.priority if s else 99
                scored.append((score, pri, pid))

            scored.sort(key=lambda x: (-x[0], x[1]))
            return [x[2] for x in scored]

    # ── Score computation (ported from scoring.ts) ────────────────────────────

    def _compute_score(
        self,
        s:       _ProviderStats,
        weights: dict[str, float],
        now:     float,
    ) -> float:
        # ── Reliability: Beta posterior expected value ───────────────────
        alpha       = s.successes + PRIOR_SUCCESS
        beta_param  = s.failures  + PRIOR_FAILURE
        reliability = alpha / (alpha + beta_param)

        # ── Speed: throughput (saturating) + TTFB (linear) ──────────────
        avg_tps    = s.total_tps  / s.tps_count    if s.tps_count    > 0 else 20.0
        avg_ttfb   = s.total_latency_ms / s.latency_count if s.latency_count > 0 else 1200.0

        throughput = 1.0 - math.exp(-avg_tps / SPEED_SCALE_TOK_S)
        ttfb_score = max(0.0, min(1.0, (TTFB_WORST_MS - avg_ttfb) / (TTFB_WORST_MS - TTFB_BEST_MS)))
        speed      = THROUGHPUT_WEIGHT * throughput + TTFB_WEIGHT * ttfb_score

        # ── Base convex combination ──────────────────────────────────────
        base = (
            weights["reliability"]   * reliability   +
            weights["speed"]         * speed         +
            weights["intelligence"]  * s.intelligence
        )

        # ── 429-penalty factor (decays over time) ────────────────────────
        if s.rate_limit_last > 0:
            elapsed      = now - s.rate_limit_last
            decay_steps  = int(elapsed / DECAY_INTERVAL_S)
            eff_penalty  = max(0.0, s.rate_limit_penalty - decay_steps * DECAY_AMOUNT)
        else:
            eff_penalty  = 0.0

        rate_limit_factor = max(0.05, 1.0 - eff_penalty / MAX_PENALTY)

        return base * rate_limit_factor

    # ── Status / observability ────────────────────────────────────────────────

    def get_status(self) -> list[dict]:
        """Snapshot of all providers sorted by score. Used by /api/provider/status."""
        now = time.monotonic()
        result: list[dict] = []
        with self._lock:
            weights = BANDIT_PRESETS.get(self._strategy, BANDIT_PRESETS["balanced"])
            for pid, s in self._stats.items():
                score = self._compute_score(s, weights, now)
                alpha = s.successes + PRIOR_SUCCESS
                beta_ = s.failures  + PRIOR_FAILURE
                result.append({
                    "provider_id":       pid,
                    "strategy":          self._strategy,
                    "score":             round(score,      3),
                    "reliability":       round(alpha / (alpha + beta_), 3),
                    "successes":         int(s.successes),
                    "failures":          int(s.failures),
                    "consecutive_5xx":   s.consecutive_5xx,
                    "rate_limit_count":  s.rate_limit_count,
                    "rate_limit_penalty": round(s.rate_limit_penalty, 1),
                    "healthy":           s.health_skip_until <= now,
                    "avg_latency_ms":    round(s.total_latency_ms / s.latency_count, 0) if s.latency_count > 0 else None,
                    "avg_tps":           round(s.total_tps / s.tps_count, 1)           if s.tps_count > 0 else None,
                    "intelligence":      s.intelligence,
                    "priority":          s.priority,
                })
        result.sort(key=lambda x: x["score"], reverse=True)
        return result

    def set_strategy(self, strategy: RoutingStrategy) -> None:
        with self._lock:
            self._strategy = strategy

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensure(self, provider_id: str) -> _ProviderStats:
        if provider_id not in self._stats:
            self._stats[provider_id] = _ProviderStats(provider_id=provider_id)
        return self._stats[provider_id]


# ── Module-level singleton ────────────────────────────────────────────────────
# llm_manager.py imports this singleton. Thread-safe: all methods acquire _lock.
_router = SmartRouter(default_strategy="balanced")


def get_router() -> SmartRouter:
    return _router
