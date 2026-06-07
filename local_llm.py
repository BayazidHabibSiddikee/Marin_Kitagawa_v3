import os
import json
import asyncio
import httpx
from typing import List, Dict, Any, AsyncIterator

# Import routing logic from config
from config import (
    OLLAMA_BASE_URL, OPENROUTER_BASE_URL, OPENROUTER_API_KEY,
    LOCAL_MODELS, CLOUD_FREE_MODELS, DEFAULT_MODEL
)

async def stream_local_chat(messages: List[Dict[str, str]], model: str = None, max_tokens: int = 2000) -> AsyncIterator[str]:
    """
    Stream chat completions from either a local Ollama instance or OpenRouter cloud.
    Automatically detects the provider based on the model name.
    """
    if not model:
        model = DEFAULT_MODEL

    # 1. Determine Provider
    is_local = model in LOCAL_MODELS or (":" in model and "/" not in model)
    
    if is_local:
        # --- OLLAMA PROVIDER ---
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.7,
                "stop": ["<|eot_id|>", "USER:", "ASSISTANT:"]
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as response:
                    if response.status_code != 200:
                        yield f"[Ollama Error {response.status_code}]"
                        return

                    async for line in response.aiter_lines():
                        if not line: continue
                        data = json.loads(line)
                        if "message" in data:
                            content = data["message"].get("content", "")
                            if content:
                                yield content
                        if data.get("done"):
                            break
        except Exception as e:
            yield f"[Ollama Connection Failed: {e}]"
            
    else:
        # --- OPENROUTER / CLOUD PROVIDER ---
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://github.com/HabibSiddikee",
            "X-Title": "Marin OS",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": 0.7
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", OPENROUTER_BASE_URL + "/chat/completions", headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        yield f"[OpenRouter Error {response.status_code}: {err_body.decode()}]"
                        return

                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            line = line[6:]
                        if not line or line == "[DONE]":
                            continue
                            
                        try:
                            data = json.loads(line)
                            if "choices" in data and len(data["choices"]) > 0:
                                content = data["choices"][0].get("delta", {}).get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            yield f"[Cloud Provider Failed: {e}]"
