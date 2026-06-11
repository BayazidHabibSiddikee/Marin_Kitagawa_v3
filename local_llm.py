import os
import json
import asyncio
import httpx
from typing import List, Dict, Any, AsyncIterator

# Import routing logic from config
from config import (
    OLLAMA_BASE_URL, LOCAL_MODELS, CLOUD_FREE_MODELS, DEFAULT_MODEL
)

async def stream_local_chat(messages: List[Dict[str, str]], model: str = None, max_tokens: int = 2000) -> AsyncIterator[str]:
    """
    Stream chat completions from a local Ollama instance.
    """
    if not model:
        model = DEFAULT_MODEL

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
