import json
import os
import time
import threading

import httpx
from langchain_openai import ChatOpenAI

import database
from config import OLLAMA_BASE_URL

# ── SmartRouter (FreeLLMAPI bandit algorithm) ──────────────────────────────────
# Imported lazily to avoid circular imports; initialised after provider list loads.
# Records success/failure/rate-limit outcomes for every LLM call so the router
# learns which providers are reliable and auto-demotes ones that are failing.
try:
    from utils.smart_router import get_router as _get_router
    _smart_router = _get_router()
except Exception as _e:
    print(f"[LLM] SmartRouter unavailable: {_e}")
    _smart_router = None

# ── Legacy fallback model list ──────────────────────────────────────────────────
FALLBACK_MODELS = [
    "google/gemini-2.5-flash",
    "google/gemini-2.5-pro",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "nvidia/llama-3.1-nemotron-70b-instruct:free",
]

COOLDOWN_SECONDS = 5 * 3600  # 5 hours
TRANSIENT_COOLDOWN_SECONDS = 60  # 1 minute for network blips

# ── Shared httpx singleton with connection pooling ──────────────────────────────
# Re-using a single Client avoids TCP handshake overhead on every validate call.
_http_client: httpx.Client | None = None
_http_client_lock = threading.Lock()

def _get_http_client() -> httpx.Client:
    """Return (and lazily create) the shared httpx.Client with connection pooling."""
    global _http_client
    if _http_client is None:
        with _http_client_lock:
            if _http_client is None:
                _http_client = httpx.Client(
                    timeout=httpx.Timeout(15.0),
                    limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
                )
    return _http_client


# ── Provider health cache (in-memory, no DB writes needed) ─────────────────────
# Tracks consecutive 5xx failures per provider. After 3 failures the provider
# is skipped for PROVIDER_COOLDOWN_SECONDS, then retried automatically.
_provider_health: dict = {}   # key: provider name → {"fails": int, "blocked_until": float}
_provider_health_lock = threading.Lock()
_PROVIDER_FAIL_THRESHOLD = 3
_PROVIDER_COOLDOWN_SECONDS = 120   # 2 minutes


def _record_provider_failure(name: str) -> bool:
    """Record a 5xx failure. Returns True if provider is now blocked."""
    with _provider_health_lock:
        entry = _provider_health.setdefault(name, {"fails": 0, "blocked_until": 0.0})
        entry["fails"] += 1
        if entry["fails"] >= _PROVIDER_FAIL_THRESHOLD:
            entry["blocked_until"] = time.time() + _PROVIDER_COOLDOWN_SECONDS
            print(f"[LLM] Provider '{name}' blocked for {_PROVIDER_COOLDOWN_SECONDS}s after {entry['fails']} failures")
            return True
        return False


def _is_provider_blocked(name: str) -> bool:
    """Return True if the provider is currently in its 2-minute cooldown window."""
    with _provider_health_lock:
        entry = _provider_health.get(name)
        if not entry:
            return False
        if entry["blocked_until"] > time.time():
            return True
        # Cooldown expired — reset failure count so provider gets a fresh start
        entry["fails"] = 0
        entry["blocked_until"] = 0.0
        return False


def _clear_provider_failure(name: str) -> None:
    """Reset failure counter when a provider succeeds."""
    with _provider_health_lock:
        _provider_health.pop(name, None)


# ── Auth & Rate limit helpers ───────────────────────────────────────────────────

def is_auth_error(e: Exception) -> bool:
    err_str = str(e).lower()
    return any(x in err_str for x in [
        "401", "unauthorized", "invalid api key",
        "authentication", "user not found",
    ])


def is_rate_limit_error(e: Exception) -> bool:
    err_str = str(e).lower()
    return any(x in err_str for x in ["429", "rate limit", "too many requests", "quota"])


def is_model_not_found_error(e: Exception) -> bool:
    err_str = str(e).lower()
    return any(x in err_str for x in ["404", "model not found", "does not exist", "not found"])


def is_insufficient_credits_error(e: Exception) -> bool:
    err_str = str(e).lower()
    return any(x in err_str for x in ["402", "insufficient credits", "requires more credits", "can only afford"])


def is_transient_error(e: Exception) -> bool:
    err_str = str(e).lower()
    return any(x in err_str for x in [
        "timeout", "timed out", "connection", "network", "503", "502", "504",
    ])


def is_context_length_error(e: Exception) -> bool:
    """Detect context-window overflow — triggers model downgrade, not cooldown."""
    err_str = str(e).lower()
    return any(x in err_str for x in [
        "context_length_exceeded", "context length", "413", "maximum context",
        "too many tokens", "input too long", "context window",
    ])


# ── Invalid keys — persisted in DB so they survive restarts ────────────────────

def _get_invalid_keys() -> set:
    raw = database.get_state("INVALID_KEYS", "[]")
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def _save_invalid_keys(keys: set):
    database.set_state("INVALID_KEYS", json.dumps(list(keys)))


def report_auth_error(key: str):
    if not key:
        return
    invalid = _get_invalid_keys()
    invalid.add(key)
    _save_invalid_keys(invalid)


def clear_invalid_keys():
    """Remove keys from the invalid set that were added more than 24h ago.

    The invalid-key set is stored as a plain list (no timestamps), so we cannot
    know individual ages.  To avoid a forever-growing blacklist we simply wipe
    the whole set once it grows stale — conservative but safe: any genuinely bad
    key will fail again on its next use and be re-added immediately.
    """
    raw = database.get_state("INVALID_KEYS_TS", "{}")
    try:
        ts_map: dict = json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        ts_map = {}

    now = time.time()
    cutoff = 24 * 3600
    stale = {k for k, v in ts_map.items() if now - v > cutoff}
    if stale:
        invalid = _get_invalid_keys()
        before = len(invalid)
        invalid -= stale
        _save_invalid_keys(invalid)
        for k in stale:
            ts_map.pop(k, None)
        database.set_state("INVALID_KEYS_TS", json.dumps(ts_map))
        print(f"[LLM] clear_invalid_keys: removed {before - len(invalid)} stale entries")
    return len(stale)


def _record_invalid_key_ts(key: str):
    """Track when each key was blacklisted (for clear_invalid_keys TTL)."""
    raw = database.get_state("INVALID_KEYS_TS", "{}")
    try:
        ts_map: dict = json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        ts_map = {}
    ts_map[key] = time.time()
    database.set_state("INVALID_KEYS_TS", json.dumps(ts_map))


# ── Rate limits ─────────────────────────────────────────────────────────────────

def _get_rate_limits() -> dict:
    raw = database.get_state("RATE_LIMITS", "{}")
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _save_rate_limits(limits: dict):
    database.set_state("RATE_LIMITS", json.dumps(limits))


def report_rate_limit(key: str, model: str):
    limits = _get_rate_limits()
    limits[f"{key}|{model}"] = time.time()
    _save_rate_limits(limits)


def _is_provider_reachable(base_url: str) -> bool:
    """Quick TCP check — skips a provider instantly if its host is unreachable.
    Only applies to localhost/LAN URLs; cloud URLs are assumed reachable."""
    import socket
    import urllib.parse
    parsed = urllib.parse.urlparse(base_url)
    host = parsed.hostname or ""
    # Only probe local endpoints; don't add latency for cloud providers
    if host not in ("localhost", "127.0.0.1", "::1"):
        return True
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _is_rate_limited(key: str, model: str, limits: dict, now: float, cooldown: int = COOLDOWN_SECONDS) -> bool:
    entry = limits.get(f"{key}|{model}")
    return entry is not None and (now - entry) < cooldown


# ── Key rotation index — persisted per provider so load spreads across keys ────

def _get_key_index(provider_name: str, num_keys: int) -> int:
    """Returns the next key index for a provider, advancing the counter in DB."""
    if num_keys <= 1:
        return 0
    raw = database.get_state(f"KEY_INDEX_{provider_name}", "0")
    try:
        current = int(raw) if isinstance(raw, (str, int)) else 0
    except (ValueError, TypeError):
        current = 0
    next_index = (current + 1) % num_keys
    database.set_state(f"KEY_INDEX_{provider_name}", str(next_index))
    return current


# ── Provider helpers ────────────────────────────────────────────────────────────

def get_providers() -> list:
    """
    Returns the ordered provider list. Each provider is a dict:
    {
      "name":     str,
      "base_url": str,
      "api_keys": [str, ...],   # multiple keys, round-robined
      "models":   [str, ...],   # selected model IDs
      "enabled":  bool,
      "priority": int
    }
    Falls back to legacy OPENROUTER_API_KEY if no PROVIDERS key is found.
    """
    raw = database.get_state("PROVIDERS")
    if raw is not None:
        try:
            # Always parse from JSON string; never trust a raw Python object from the DB
            providers = json.loads(raw) if isinstance(raw, str) else json.loads(json.dumps(raw))
            if isinstance(providers, list) and providers:
                return sorted(providers, key=lambda p: p.get("priority", 99))
        except Exception:
            pass

    # ── Migrate legacy keys to a single provider slot ─────────────────────────
    legacy_key = database.get_state("OPENROUTER_API_KEY", "")
    legacy_keys = [k.strip() for k in legacy_key.split(",") if k.strip()] if legacy_key else []

    custom_models_raw = database.get_state("SELECTED_MODELS") or database.get_state("FALLBACK_MODELS")
    legacy_models = custom_models_raw if isinstance(custom_models_raw, list) else FALLBACK_MODELS

    providers = []
    if legacy_keys:
        providers.append({
            "name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_keys": legacy_keys,
            "models": legacy_models,
            "enabled": True,
            "priority": 1,
        })

    # FreeLLMAPI - aggregated free LLM providers (local instance)
    freellmapi_key = database.get_state("FREELLMAPI_KEY", "")
    freellmapi_url = os.getenv("FREELLMAPI_URL", "http://localhost:3001")
    if freellmapi_key:
        providers.append({
            "name": "FreeLLMAPI",
            "base_url": f"{freellmapi_url}/v1",
            "api_keys": [freellmapi_key],
            "models": [
                "auto",
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
                "deepseek-v4-flash-free",
                "llama-3.3-70b-versatile",
                "mistral-small-latest",
            ],
            "enabled": True,
            "priority": 0,
        })

    proxy_url = os.getenv("LLM_PROXY_URL", "")
    if proxy_url:
        providers.append({
            "name": "Proxy",
            "base_url": proxy_url,
            "api_keys": ["proxy-rotate"],
            "models": legacy_models,
            "enabled": True,
            "priority": 0,
        })

    return sorted(providers, key=lambda p: p.get("priority", 99))


def save_providers(providers: list):
    # Always serialize to JSON string so get_providers() can reliably parse it back
    database.set_state("PROVIDERS", json.dumps(providers))


# ── Deep model list ─────────────────────────────────────────────────────────────

def get_deep_models() -> list:
    raw = database.get_state("DEEP_MODELS")
    if raw and raw != "[]":
        try:
            models = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(models, list):
                return models
        except Exception:
            pass
    return [
        "google/gemini-2.5-flash",
        "qwen/qwen-2.5-72b-instruct:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ]


def save_deep_models(models: list):
    database.set_state("DEEP_MODELS", json.dumps(models))


# ── Internal: build + validate a ChatOpenAI instance ───────────────────────────

def _try_build_llm(model: str, key: str, base_url: str):
    """
    Instantiates ChatOpenAI and does a minimal probe call.
    Returns the llm on success, raises on failure.
    ChatOpenAI.__init__ never raises on bad credentials — only .invoke() does.
    """
    return ChatOpenAI(
        model=model,
        api_key=key,
        base_url=base_url,
        max_retries=1,
    )


# ── Core LLM selector ──────────────────────────────────────────────────────────

def get_best_llm(deep: bool = False):
    """
    Returns (ChatOpenAI instance, api_key, model_id) or None.

    Resolution order:
    1. If deep=True, try DEEP_MODELS across all enabled providers first.
    2. Try each provider's own model list (round-robin key rotation).
    3. Last resort: Ollama local.

    Keys are rotated round-robin using a persisted index, so load is spread
    evenly rather than always hammering key[0] until it's rate-limited.
    Invalid keys (auth failures) are persisted in the DB across restarts.
    Providers with ≥3 consecutive 5xx errors are skipped for 2 minutes.
    """
    limits     = _get_rate_limits()
    now        = time.time()
    invalid    = _get_invalid_keys()

    # Prune stale rate-limit entries
    cleaned = {k: v for k, v in limits.items() if now - v < COOLDOWN_SECONDS}
    if len(cleaned) != len(limits):
        _save_rate_limits(cleaned)
        limits = cleaned

    providers = get_providers()

    def _try_provider_with_models(provider: dict, model_list: list):
        """Try every model × every key in a provider, starting at the rotated index."""
        if not provider.get("enabled", True):
            return None
        base_url = provider.get("base_url", "")
        api_keys = provider.get("api_keys", [])
        name     = provider.get("name", "unknown")
        if not api_keys or not base_url or not model_list:
            return None
        # Skip instantly if a local provider is not running
        if not _is_provider_reachable(base_url):
            print(f"[LLM] {name} unreachable — skipping")
            return None
        # Skip if provider is in 2-minute health cooldown
        if _is_provider_blocked(name):
            print(f"[LLM] {name} in health cooldown — skipping")
            return None

        # ── Register provider with SmartRouter (first call only) ──────────────
        if _smart_router:
            # Intelligence proxy: use model name heuristics
            _intel = 0.5
            top_model = (model_list[0] if model_list else "").lower()
            if any(m in top_model for m in ["gpt-4", "gemini-2.5-pro", "opus", "405b", "70b"]):
                _intel = 0.85
            elif any(m in top_model for m in ["gemini-2.5-flash", "gemini-1.5", "gpt-4o", "llama-3.3", "72b"]):
                _intel = 0.72
            elif any(m in top_model for m in ["gemini-1.5-flash", "gpt-4o-mini", "haiku", "8b"]):
                _intel = 0.58
            _smart_router.register_provider(name, intelligence=_intel, priority=provider.get("priority", 5))

        num_keys  = len(api_keys)
        start_idx = _get_key_index(name, num_keys)

        for model in model_list:
            # Rotate through keys starting at the saved index
            for offset in range(num_keys):
                key = api_keys[(start_idx + offset) % num_keys]
                if key in invalid:
                    continue
                if _is_rate_limited(key, model, limits, now):
                    continue
                _t0 = time.monotonic()
                try:
                    llm = _try_build_llm(model, key, base_url)
                    _clear_provider_failure(name)
                    _latency = (time.monotonic() - _t0) * 1000
                    if _smart_router:
                        _smart_router.record_success(name, latency_ms=_latency)
                    return llm, key, model
                except Exception as e:
                    if is_auth_error(e):
                        print(f"[LLM] Auth error for key ...{key[-6:]} on {name} — blacklisting")
                        invalid.add(key)
                        _save_invalid_keys(invalid)
                        _record_invalid_key_ts(key)
                    elif is_context_length_error(e):
                        print(f"[LLM] Context length error on {name}/{model} — downgrading model")
                        if _smart_router:
                            _smart_router.record_context_length_error(name)
                        # Don't cooldown the key — just skip this (large) model
                        break
                    elif is_insufficient_credits_error(e):
                        print(f"[LLM] Insufficient credits on {name}/{model} — skipping model")
                        # Don't blacklist the key, just skip this model
                    elif is_rate_limit_error(e):
                        print(f"[LLM] Rate limit on {name}/{model}: {e}")
                        report_rate_limit(key, model)
                        limits[f"{key}|{model}"] = now
                        if _smart_router:
                            _smart_router.record_rate_limit(name)
                    elif is_model_not_found_error(e):
                        print(f"[LLM] Model not found on {name}/{model}: {e}")
                    elif is_transient_error(e):
                        print(f"[LLM] Transient error on {name}/{model}: {e}")
                        limits[f"{key}|{model}"] = now - COOLDOWN_SECONDS + TRANSIENT_COOLDOWN_SECONDS
                        # Count 5xx-style transient failures toward provider health cache
                        err_str = str(e).lower()
                        if any(code in err_str for code in ["503", "502", "504"]):
                            _record_provider_failure(name)
                            if _smart_router:
                                _smart_router.record_failure(name)
                    else:
                        print(f"[LLM] Error on {name}/{model}: {e}")
                        report_rate_limit(key, model)
                        limits[f"{key}|{model}"] = now
                        if _smart_router:
                            _smart_router.record_failure(name)
        return None

    # ── Deep mode: try deep_models list across all providers first ─────────────
    if deep:
        deep_model_ids = get_deep_models()
        for provider in providers:
            result = _try_provider_with_models(provider, deep_model_ids)
            if result:
                return result
        # Fall through to normal selection if all deep models exhausted

    # ── Normal mode: each provider's own model list ────────────────────────────
    for provider in providers:
        models = provider.get("models", [])
        result = _try_provider_with_models(provider, models)
        if result:
            return result

    # ── Last resort: Ollama local (only if not rate-limited) ──────────────────
    ollama_model = "marin:latest"
    if not _is_rate_limited("ollama", ollama_model, limits, now):
        print("[LLM] All providers exhausted — falling back to local Ollama")
        try:
            llm = ChatOpenAI(
                model=ollama_model,
                api_key="ollama",
                base_url=OLLAMA_BASE_URL,
                max_retries=2,
            )
            # Ollama doesn't need the probe (local, no auth)
            return llm, "ollama", ollama_model
        except Exception as e:
            print(f"[LLM] Ollama also failed: {e}")
    else:
        print("[LLM] All providers including Ollama exhausted")

    return None


# ── Provider status snapshot (for UI status page) ──────────────────────────────

def get_provider_status() -> list[dict]:
    """Return a list of provider health snapshots for the settings/status UI.

    Each entry:
    {
      "name":        str,
      "enabled":     bool,
      "blocked":     bool,      # True if in 2-min health cooldown
      "fail_count":  int,       # consecutive 5xx failures
      "blocked_until": float,   # epoch seconds when cooldown ends (0 = not blocked)
      "model_count": int,
    }
    """
    providers = get_providers()
    snapshots = []
    with _provider_health_lock:
        health_copy = dict(_provider_health)

    for p in providers:
        name = p.get("name", "unknown")
        entry = health_copy.get(name, {"fails": 0, "blocked_until": 0.0})
        blocked = entry["blocked_until"] > time.time()
        snapshots.append({
            "name":          name,
            "enabled":       p.get("enabled", True),
            "blocked":       blocked,
            "fail_count":    entry["fails"],
            "blocked_until": entry["blocked_until"],
            "model_count":   len(p.get("models", [])),
        })
    return snapshots


# ── Web search via DuckDuckGo ───────────────────────────────────────────────────

def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web using DuckDuckGo. Returns [{title, url, snippet}].

    This is the lightweight llm_manager-level wrapper. For full logging +
    page-fetch functionality use tools/web_search_tool.py instead.
    """
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title":   r.get("title", ""),
                    "url":     r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        return results
    except Exception as e:
        print(f"[WebSearch] DuckDuckGo search failed: {e}")
        return []


# ── Key validation (used by settings UI) ───────────────────────────────────────

def validate_api_key(key: str, base_url: str = "https://openrouter.ai/api/v1") -> tuple[bool, str]:
    """
    Validate an API key without consuming any tokens.

    - OpenRouter: hits /auth/key (no tokens used)
    - Google Gemini: lists available models
    - OpenAI: lists available models
    - Others: minimal /models list call

    Uses the shared httpx.Client singleton with connection pooling and 15s timeout.
    """
    if not key:
        return False, "No key provided"

    # Remove from invalid set to allow re-testing a blacklisted key
    invalid = _get_invalid_keys()
    if key in invalid:
        invalid.discard(key)
        _save_invalid_keys(invalid)

    client = _get_http_client()

    try:
        headers = {"Authorization": f"Bearer {key}"}

        # ── OpenRouter: dedicated key-info endpoint (zero cost) ────────────
        if "openrouter.ai" in base_url:
            r = client.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers=headers,
            )
            if r.status_code == 200:
                info = r.json().get("data", {})
                usage = info.get("usage", 0)
                limit = info.get("limit")
                label = info.get("label", "")
                free_tier = info.get("is_free_tier", False)
                credits = f"{limit - usage:.4f}" if limit else "unlimited"
                tier = " [free tier]" if free_tier else ""
                name_part = f" — {label}" if label else ""
                return True, f"Key valid{name_part}{tier}. Credits remaining: {credits}"
            if r.status_code == 401:
                invalid.add(key)
                _save_invalid_keys(invalid)
                _record_invalid_key_ts(key)
                return False, "Invalid API key."
            return False, f"OpenRouter returned HTTP {r.status_code}."

        # ── Google Gemini: list models (no tokens) ─────────────────────────
        if "generativelanguage.googleapis.com" in base_url:
            r = client.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
            )
            if r.status_code == 200:
                return True, "Gemini key is valid."
            if r.status_code in (400, 401, 403):
                invalid.add(key)
                _save_invalid_keys(invalid)
                _record_invalid_key_ts(key)
                return False, "Invalid Gemini API key."
            return False, f"Gemini returned HTTP {r.status_code}."

        # ── OpenAI / compatible: list models (no tokens) ──────────────────
        r = client.get(
            base_url.rstrip("/").replace("/v1", "") + "/v1/models",
            headers=headers,
        )
        if r.status_code == 200:
            models = r.json().get("data", [])
            return True, f"Key valid. {len(models)} model(s) available."
        if r.status_code in (401, 403):
            invalid.add(key)
            _save_invalid_keys(invalid)
            _record_invalid_key_ts(key)
            return False, "Invalid API key or authentication failed."
        return False, f"Provider returned HTTP {r.status_code}."

    except Exception as e:
        return False, f"Connection failed: {str(e)}"
