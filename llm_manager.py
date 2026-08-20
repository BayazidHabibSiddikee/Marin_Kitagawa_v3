import json
import os
import time

from langchain_openai import ChatOpenAI

import database
from config import OLLAMA_BASE_URL

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

        num_keys   = len(api_keys)
        start_idx  = _get_key_index(name, num_keys)

        for model in model_list:
            # Rotate through keys starting at the saved index
            for offset in range(num_keys):
                key = api_keys[(start_idx + offset) % num_keys]
                if key in invalid:
                    continue
                if _is_rate_limited(key, model, limits, now):
                    continue
                try:
                    llm = _try_build_llm(model, key, base_url)
                    return llm, key, model
                except Exception as e:
                    if is_auth_error(e):
                        print(f"[LLM] Auth error for key ...{key[-6:]} on {name} — blacklisting")
                        invalid.add(key)
                        _save_invalid_keys(invalid)
                    elif is_insufficient_credits_error(e):
                        print(f"[LLM] Insufficient credits on {name}/{model} — skipping model")
                        # Don't blacklist the key, just skip this model
                    elif is_rate_limit_error(e):
                        print(f"[LLM] Rate limit on {name}/{model}: {e}")
                        report_rate_limit(key, model)
                        limits[f"{key}|{model}"] = now
                    elif is_model_not_found_error(e):
                        print(f"[LLM] Model not found on {name}/{model}: {e}")
                    elif is_transient_error(e):
                        print(f"[LLM] Transient error on {name}/{model}: {e}")
                        limits[f"{key}|{model}"] = now - COOLDOWN_SECONDS + TRANSIENT_COOLDOWN_SECONDS
                    else:
                        print(f"[LLM] Error on {name}/{model}: {e}")
                        report_rate_limit(key, model)
                        limits[f"{key}|{model}"] = now
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


# ── Key validation (used by settings UI) ───────────────────────────────────────

def validate_api_key(key: str, base_url: str = "https://openrouter.ai/api/v1") -> tuple[bool, str]:
    """
    Validate an API key without consuming any tokens.

    - OpenRouter: hits /auth/key (no tokens used)
    - Google Gemini: lists available models
    - OpenAI: lists available models
    - Others: minimal /models list call
    """
    import httpx

    if not key:
        return False, "No key provided"

    # Remove from invalid set to allow re-testing a blacklisted key
    invalid = _get_invalid_keys()
    if key in invalid:
        invalid.discard(key)
        _save_invalid_keys(invalid)

    try:
        headers = {"Authorization": f"Bearer {key}"}

        # ── OpenRouter: dedicated key-info endpoint (zero cost) ────────────
        if "openrouter.ai" in base_url:
            r = httpx.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers=headers,
                timeout=10.0,
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
                return False, "Invalid API key."
            return False, f"OpenRouter returned HTTP {r.status_code}."

        # ── Google Gemini: list models (no tokens) ─────────────────────────
        if "generativelanguage.googleapis.com" in base_url:
            r = httpx.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                timeout=10.0,
            )
            if r.status_code == 200:
                return True, "Gemini key is valid."
            if r.status_code in (400, 401, 403):
                invalid.add(key)
                _save_invalid_keys(invalid)
                return False, "Invalid Gemini API key."
            return False, f"Gemini returned HTTP {r.status_code}."

        # ── OpenAI / compatible: list models (no tokens) ──────────────────
        r = httpx.get(
            base_url.rstrip("/").replace("/v1", "") + "/v1/models",
            headers=headers,
            timeout=10.0,
        )
        if r.status_code == 200:
            models = r.json().get("data", [])
            return True, f"Key valid. {len(models)} model(s) available."
        if r.status_code in (401, 403):
            invalid.add(key)
            _save_invalid_keys(invalid)
            return False, "Invalid API key or authentication failed."
        return False, f"Provider returned HTTP {r.status_code}."

    except Exception as e:
        return False, f"Connection failed: {str(e)}"
