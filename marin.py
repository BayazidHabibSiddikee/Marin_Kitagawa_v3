import os
import re
import json
import asyncio
import datetime
import threading
from typing import AsyncIterator, Optional, Dict, Any

import httpx
from langgraph_agent import stream_chat_with_marin
from utils.persona import get_character_prompt, analyze_marin_vibe
from utils.security import apply_friction, log_command
from privilege_manager import get_privilege_manager, get_role, cold_latency
import database

# ── CONFIG ──────────────────────────────────────────────────────────────────
OWNER_USER = os.getenv("OWNER_USER", "Bayazid")
RAG_ENABLED = True
VOICE_ENABLED = False

# ── MAIN ENTRY POINT ────────────────────────────────────────────────────────

async def main(prompt: str, image_path: str = None, user: dict = None, session_id: str = "default"):
    """
    Main entry point for Marin Tools.
    Unified flow: Security -> Preprocess -> Orchestrate -> Deliver.
    """
    user = user or {"user_id": "USR-00000000", "username": "guest", "role": "guest"}
    user_id = user["user_id"]
    is_owner = (user["role"] == "owner")
    
    pm = get_privilege_manager()
    
    # 1. Security check
    cold_latency(user, confidence=1.0)
    await apply_friction(user_id, is_owner=is_owner)
    
    if not pm.check_quota(user_id):
        yield "[QUOTA EXCEEDED] Systems restricted. Access denied."
        return
    pm.use_quota(user_id)

    # 2. Preprocess (Market Data, RAG, etc.)
    # Injected into the context via LangGraph
    from utils.agent_logic import preprocess_input
    prep = await preprocess_input(prompt, image_path=image_path, rag_enabled=RAG_ENABLED)
    
    # 3. Load History
    history = database.get_history("marin", limit=20, user_id=user_id, session_id=session_id)
    
    # 4. Stream from Agent
    full_response = ""
    user_vibe = prep["classification"].get("user_vibe", "neutral")
    
    async for chunk in stream_chat_with_marin(
        prompt,
        history=history,
        context=prep["enriched_prompt"],
        user_id=user_id,
        role=user["role"],
        user_vibe=user_vibe
    ):
        # Apply output sanitization
        clean = pm.sanitize_response(chunk, user)
        yield clean
        full_response += clean

    # 5. Finalize
    if full_response:
        database.save_message("marin", "user", prompt, user_id=user_id, session_id=session_id)
        database.save_message("marin", "assistant", full_response, user_id=user_id, session_id=session_id)
        
        # Analyze and log
        vibe = analyze_marin_vibe(full_response)
        yield f"__VIBE__{vibe}"

if __name__ == "__main__":
    # CLI mode
    async def run_cli():
        prompt = input(">> ")
        async for chunk in main(prompt):
            print(chunk, end="", flush=True)
        print()
    asyncio.run(run_cli())
