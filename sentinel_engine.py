import asyncio
import json
import logging
import os
import subprocess
import time
from collections import defaultdict

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

# ── Logging ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "logs", "sentinel.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger("sentinel")

from config import DEFAULT_MODEL, OLLAMA_BASE_URL

DEFAULT_LOCAL_MODEL = DEFAULT_MODEL
DEFAULT_CLOUD_MODEL = "google/gemma-4-31b-it:free"

# ── Key Management ──────────────────────────────────────────────────────────────
KEYS_FILE = os.path.join(BASE_DIR, "storage", "api_keys.txt")
os.makedirs(os.path.dirname(KEYS_FILE), exist_ok=True)

class KeyPool:
    """Round-robin key pool with per-key failure tracking."""
    def __init__(self):
        self.keys: list[str] = []
        self.index: int = 0
        self.fail_count: dict[str, int] = defaultdict(int)
        self.last_used: dict[str, float] = {}
        self.total_requests: dict[str, int] = defaultdict(int)
        self.reload()

    def reload(self):
        self.keys = []
        if os.path.exists(KEYS_FILE):
            with open(KEYS_FILE) as f:
                for line in f:
                    k = line.strip()
                    if k and not k.startswith("#"):
                        self.keys.append(k)
        # If no keys exist, seed it with the ones from settings or vault if available
        if not self.keys:
            from config import API_KEYS
            for k, v in API_KEYS.items():
                if v.get("api_key"):
                    self.keys.append(v["api_key"])
            if self.keys:
                self.save(self.keys)
        logger.info(f"Loaded {len(self.keys)} keys from api_keys.txt")

    def save(self, keys: list[str]):
        with open(KEYS_FILE, "w") as f:
            f.write("\n".join(keys))
        self.reload()

    @property
    def or_keys(self):
        return [k for k in self.keys if k.startswith("sk-")]

    @property
    def ollama_keys(self):
        return [k for k in self.keys if not k.startswith("sk-")]

    def next_or_key(self) -> str | None:
        active = self.or_keys
        if not active:
            return None
        key = active[self.index % len(active)]
        self.index = (self.index + 1) % len(active)
        self.last_used[key] = time.time()
        self.total_requests[key] += 1
        return key

    def mark_failed(self, key: str):
        self.fail_count[key] += 1

    def stats(self):
        result = []
        for k in self.keys:
            kind = "OpenRouter" if k.startswith("sk-") else "Ollama"
            result.append({
                "key": k[:18] + "…",
                "type": kind,
                "requests": self.total_requests[k],
                "failures": self.fail_count[k],
                "last_used": self.last_used.get(k),
            })
        return result

pool = KeyPool()

# ── Proxy Stats ─────────────────────────────────────────────────────────────────
stats = {
    "total": 0,
    "openrouter": 0,
    "ollama": 0,
    "errors": 0,
    "start_time": time.time(),
}

# ── App ─────────────────────────────────────────────────────────────────────────
sentinel_app = FastAPI(title="Marin Sentinel Proxy")

# ── Shared HTTP Client ──────────────────────────────────────────────────────────
# Using a single AsyncClient pool dramatically speeds up proxying by reusing connections
_http_client: httpx.AsyncClient | None = None

@sentinel_app.on_event("startup")
async def startup_event():
    global _http_client
    _http_client = httpx.AsyncClient(timeout=180.0, limits=httpx.Limits(max_keepalive_connections=50, max_connections=100))

@sentinel_app.on_event("shutdown")
async def shutdown_event():
    global _http_client
    if _http_client:
        await _http_client.aclose()

# ── Helpers ─────────────────────────────────────────────────────────────────────
def is_local_model(model: str) -> bool:
    """Heuristic: if no slash, treat as local unless we have OR keys."""
    return "/" not in model and not pool.or_keys

async def stream_proxy(url: str, body: dict, headers: dict):
    async def gen():
        try:
            # We use an ephemeral client for streaming to avoid holding connection pool slots indefinitely
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("POST", url, json=body, headers=headers) as resp:
                    if resp.status_code != 200:
                        err = await resp.aread()
                        logger.error(f"Upstream {resp.status_code}: {err.decode()[:300]}")
                        yield f"data: {json.dumps({'error': err.decode()})}\n\n".encode()
                        return
                    async for line in resp.aiter_lines():
                        if line:
                            yield (line + "\n").encode()
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n".encode()
    return StreamingResponse(gen(), media_type="text/event-stream")

def start_ollama():
    try:
        subprocess.Popen(
            ["nohup", "ollama", "serve"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setpgrp,
        )
        logger.info("Ollama started.")
    except Exception as e:
        logger.warning(f"Could not start Ollama: {e}")

# ── Chat Completions ─────────────────────────────────────────────────────────────
@sentinel_app.post("/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model = body.get("model", "")
    streaming = body.get("stream", False)
    stats["total"] += 1

    # ── Try OpenRouter (Only for cloud models) ────────────────────────────────
    if pool.or_keys and "/" in model:
        or_keys = pool.or_keys
        for attempt in range(len(or_keys)):
            key = pool.next_or_key()
            if not key:
                break
            req_body = body.copy()

            headers = {
                "Authorization": f"Bearer {key}",
                "HTTP-Referer": "https://github.com/BayazidHabibSiddikee",
                "X-Title": "Marin OS Sentinel",
                "Content-Type": "application/json",
            }
            logger.info(f"[OR] key={key[:18]}… model={req_body['model']} stream={streaming}")
            try:
                if streaming:
                    stats["openrouter"] += 1
                    return await stream_proxy(
                        "https://openrouter.ai/api/v1/chat/completions", req_body, headers
                    )

                resp = await _http_client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=req_body, headers=headers,
                )
                if resp.status_code == 200:
                    stats["openrouter"] += 1
                    return resp.json()
                logger.warning(f"[OR] key={key[:18]}… status={resp.status_code} body={resp.text[:200]}")
                pool.mark_failed(key)
                # 5xx = server-side error → keep trying next key (don't bail)
                # 4xx that are NOT rate-limit or auth failures → give up (bad request)
                if 400 <= resp.status_code < 500 and resp.status_code not in (429, 401, 403):
                    break
            except httpx.TimeoutException:
                logger.warning(f"[OR] key={key[:18]}… timed out")
                pool.mark_failed(key)
            except Exception as e:
                logger.error(f"[OR] key={key[:18]}… error: {e}")
                pool.mark_failed(key)

        logger.warning("All OpenRouter keys exhausted. Falling back to Ollama.")

    # ── Ollama Fallback ───────────────────────────────────────────────────────
    logger.info(f"[Ollama] model={model}")
    req_body = body.copy()
    if "/" in model:
        req_body["model"] = DEFAULT_LOCAL_MODEL
        logger.info(f"Cloud model requested but routing to Ollama → {DEFAULT_LOCAL_MODEL}")

    headers = {"Content-Type": "application/json"}
    if pool.ollama_keys:
        headers["Authorization"] = f"Bearer {pool.ollama_keys[0]}"

    try:
        # Use Ollama's OpenAI-compatible endpoint
        ollama_url = f"{OLLAMA_BASE_URL}/v1/chat/completions" if "v1" not in OLLAMA_BASE_URL else f"{OLLAMA_BASE_URL}/chat/completions"

        if streaming:
            stats["ollama"] += 1
            return await stream_proxy(ollama_url, req_body, headers)

        # Retry loop — Ollama can be slow to warm up on first boot
        last_status = None
        for attempt in range(3):
            try:
                resp = await _http_client.post(ollama_url, json=req_body, headers=headers)
                if resp.status_code == 200:
                    stats["ollama"] += 1
                    return resp.json()
                last_status = resp.status_code
                logger.warning(f"[Ollama] attempt {attempt + 1}/3 — status={last_status}")
            except httpx.ConnectError as ce:
                last_status = "ConnectError"
                logger.warning(f"[Ollama] attempt {attempt + 1}/3 — connect error: {ce}")
                start_ollama()
            if attempt < 2:
                await asyncio.sleep(1)
        logger.error(f"[Ollama] all retries failed — last status={last_status}")
    except Exception as e:
        logger.error(f"[Ollama] unreachable: {e}")
        start_ollama()

    stats["errors"] += 1
    raise HTTPException(status_code=503, detail="All providers failed. Check sentinel.log for details.")

# ── Native Module Interfaces (No HTTP Loopback) ────────────────────────────────
def get_langchain_model(model_name: str, bind_tools: list | None = None, **kwargs):
    """Native LangChain factory. Uses llm_manager for provider/key selection,
    falls back to the legacy sentinel key pool, then Ollama."""
    from langchain_ollama import ChatOllama
    from langchain_openai import ChatOpenAI

    # ── Primary: use llm_manager's multi-provider selector ────────────────────
    try:
        import llm_manager
        result = llm_manager.get_best_llm()
        if result:
            llm, key, model = result
            if bind_tools:
                llm = llm.bind_tools(bind_tools)
            return llm
    except Exception as e:
        logger.warning(f"llm_manager.get_best_llm failed: {e}")

    # ── Fallback: legacy sentinel key pool (OpenRouter) ────────────────────────
    if "/" in model_name and pool.or_keys:
        llms = []
        start_idx = pool.index
        ordered_keys = [pool.or_keys[(start_idx + i) % len(pool.or_keys)] for i in range(len(pool.or_keys))]
        pool.index = (pool.index + 1) % len(pool.or_keys)

        for key in ordered_keys:
            llm = ChatOpenAI(
                model=model_name,
                api_key=key,
                base_url="https://openrouter.ai/api/v1",
                max_retries=0,
                timeout=120,
                **kwargs
            )
            if bind_tools:
                llm = llm.bind_tools(bind_tools)
            llms.append(llm)

        primary = llms[0]
        if len(llms) > 1:
            primary = primary.with_fallbacks(llms[1:])
        return primary

    # ── Last resort: local Ollama ──────────────────────────────────────────────
    if "/" in model_name:
        model_name = DEFAULT_LOCAL_MODEL
    llm = ChatOllama(model=model_name, base_url=OLLAMA_BASE_URL, timeout=120, **kwargs)

    if pool.or_keys:
        cloud_fallbacks = []
        for key in pool.or_keys:
            cloud_llm = ChatOpenAI(
                model=DEFAULT_CLOUD_MODEL,
                api_key=key,
                base_url="https://openrouter.ai/api/v1",
                max_retries=0,
                timeout=120,
                **kwargs
            )
            if bind_tools:
                cloud_llm = cloud_llm.bind_tools(bind_tools)
            cloud_fallbacks.append(cloud_llm)
        if bind_tools:
            llm = llm.bind_tools(bind_tools)
        return llm.with_fallbacks(cloud_fallbacks)

    if bind_tools:
        llm = llm.bind_tools(bind_tools)
    return llm

async def stream_chat_native(model: str, messages: list, max_tokens: int = 4096):
    """Native async generator for local_llm.py to bypass localhost HTTP."""
    req_body = {
        "model": model,
        "messages": messages,
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": 0.7
    }

    if pool.or_keys and "/" in model:
        for _attempt in range(len(pool.or_keys)):
            key = pool.next_or_key()
            headers = {
                "Authorization": f"Bearer {key}",
                "HTTP-Referer": "https://github.com/BayazidHabibSiddikee",
                "X-Title": "Marin OS Sentinel",
                "Content-Type": "application/json",
            }
            try:
                async for chunk in _stream_native("https://openrouter.ai/api/v1/chat/completions", req_body, headers):
                    yield chunk
                return # Success
            except Exception as e:
                pool.mark_failed(key)
                logger.warning(f"Native stream OR fallback triggered: {e}")

    # Ollama Fallback
    if "/" in model:
        req_body["model"] = DEFAULT_LOCAL_MODEL
    headers = {"Content-Type": "application/json"}
    ollama_url = f"{OLLAMA_BASE_URL}/v1/chat/completions" if "v1" not in OLLAMA_BASE_URL else f"{OLLAMA_BASE_URL}/chat/completions"
    try:
        async for chunk in _stream_native(ollama_url, req_body, headers):
            yield chunk
    except Exception as e:
        logger.error(f"Ollama stream unreachable: {e}")
        start_ollama()
        yield "I couldn't reach Ollama! I tried to start it automatically, but please make sure it is running on your host machine."

async def _stream_native(url: str, body: dict, headers: dict):
    """Helper to yield just the text chunks from an SSE stream."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, json=body, headers=headers) as resp:
            if resp.status_code != 200:
                err = await resp.aread()
                raise Exception(f"HTTP {resp.status_code}: {err.decode()}")
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or line == "data: [DONE]": continue
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if "choices" in data and len(data["choices"]) > 0:
                            content = data["choices"][0].get("delta", {}).get("content", "")
                            if content: yield content
                    except json.JSONDecodeError:
                        pass

# ── Admin API ────────────────────────────────────────────────────────────────────
# Admin authentication - requires X-Admin-Key header
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "marin-admin-key-change-me")

def verify_admin_auth(request: Request) -> bool:
    """Verify admin API key from request header."""
    auth_header = request.headers.get("X-Admin-Key", "")
    return auth_header == ADMIN_API_KEY

@sentinel_app.get("/admin/stats")
async def admin_stats(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(401, "Invalid admin key")
    uptime = int(time.time() - stats["start_time"])
    return {
        **stats,
        "uptime_seconds": uptime,
        "keys": pool.stats(),
        "or_key_count": len(pool.or_keys),
        "ollama_key_count": len(pool.ollama_keys),
    }

@sentinel_app.get("/admin/keys")
async def admin_keys(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(401, "Invalid admin key")
    return {"keys": pool.keys, "count": len(pool.keys)}

@sentinel_app.post("/admin/keys/add")
async def admin_add_key(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(401, "Invalid admin key")
    data = await request.json()
    new_key = data.get("key", "").strip()
    if not new_key:
        raise HTTPException(400, "key is required")
    if new_key in pool.keys:
        raise HTTPException(409, "Key already exists")
    pool.save(pool.keys + [new_key])
    return {"ok": True, "total": len(pool.keys)}

@sentinel_app.post("/admin/keys/remove")
async def admin_remove_key(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(401, "Invalid admin key")
    data = await request.json()
    key = data.get("key", "").strip()
    remaining = [k for k in pool.keys if k != key]
    pool.save(remaining)
    return {"ok": True, "total": len(pool.keys)}

@sentinel_app.post("/admin/keys/reload")
async def admin_reload(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(401, "Invalid admin key")
    pool.reload()
    return {"ok": True, "total": len(pool.keys)}

# ── Health ────────────────────────────────────────────────────────────────────────
@sentinel_app.get("/health")
async def health():
    return {"status": "ok", "uptime": int(time.time() - stats["start_time"])}
