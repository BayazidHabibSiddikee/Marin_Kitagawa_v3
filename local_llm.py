from collections.abc import AsyncIterator

# Import routing logic from config
from config import DEFAULT_MODEL


async def stream_local_chat(messages: list[dict[str, str]], model: str | None = None, max_tokens: int = 2000) -> AsyncIterator[str]:
    """
    Stream chat completions from a local Ollama instance.
    """
    if not model:
        model = DEFAULT_MODEL

    from sentinel_engine import stream_chat_native

    try:
        async for chunk in stream_chat_native(model, messages, max_tokens):
            yield chunk
    except Exception as e:
        yield f"[LLM Connection Failed: {e}]"
