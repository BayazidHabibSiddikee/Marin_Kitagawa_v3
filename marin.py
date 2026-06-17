import os
import re
import json
import asyncio
import datetime
import threading
from typing import AsyncIterator, Optional, Dict, Any

import httpx
from utils.persona import get_character_prompt, analyze_marin_vibe
from utils.security import apply_friction, log_command
import database

# ── CONFIG (canonical location for runtime toggles) ──────────────────────
OWNER_USER = os.getenv("OWNER_USER", "Bayazid")
RAG_ENABLED = True
VOICE_ENABLED = True
WORD_LIMIT = 0  # 0 = unlimited

# ── PENDING CONFIRMATIONS (stub for command_api.py HITL) ─────────────────
# Maps confirmation IDs to pending actions so the user can approve/reject
PENDING_CONFIRMATIONS: Dict[str, dict] = {}
_confirm_counter = 0


def request_confirmation(cmd: str, user: str = "USR-MASTER") -> str:
    """Queue a command for owner confirmation. Returns confirmation ID."""
    global _confirm_counter
    _confirm_counter += 1
    cid = f"CONFIRM-{_confirm_counter:04d}"
    PENDING_CONFIRMATIONS[cid] = {
        "cmd": cmd,
        "user": user,
        "ts": datetime.datetime.now().isoformat(),
        "status": "pending",
        "result": None,
    }
    print(f"[HITL] Queued for confirmation: {cid} -> {cmd[:60]}")
    return cid


def _check_confirmation(cid: str, approved: bool) -> bool:
    """Approve or reject a pending confirmation."""
    entry = PENDING_CONFIRMATIONS.get(cid)
    if not entry or entry["status"] != "pending":
        return False
    entry["status"] = "approved" if approved else "rejected"
    return True


# ── MAIN ENTRY POINT ────────────────────────────────────────────────────

async def main(prompt: str, image_path: str = None, user: dict = None, session_id: str = "default"):
    """
    Main entry point for Marin Tools.
    Unified flow: Security -> Preprocess -> Orchestrate -> Deliver.
    """
    user = user or {"user_id": "USR-00000000", "username": "guest", "role": "guest"}
    user_id = user["user_id"]
    is_owner = (user["role"] == "owner")

    from privilege_manager import get_privilege_manager, cold_latency

    pm = get_privilege_manager()

    # 1. Security check (pass user_id string, not the dict)
    cold_latency(user_id, confidence=1.0)
    await apply_friction(user_id, is_owner=is_owner)

    if not pm.check_quota(user_id):
        yield "[QUOTA EXCEEDED] Systems restricted. Access denied."
        return
    pm.use_quota(user_id)

    # 2. Preprocess (Market Data, RAG, etc.)
    from utils.agent_logic import preprocess_input
    prep = await preprocess_input(prompt, image_path=image_path, rag_enabled=RAG_ENABLED)

    # 3. Load History
    history = database.get_history("marin", limit=20, user_id=user_id, session_id=session_id)

    # 4. Stream from Agent
    from utils.agent_logic import stream_marin_chat
    full_response = ""
    user_vibe = prep["classification"].get("user_vibe", "neutral")

    async for chunk in stream_marin_chat(
        prompt,
        user=user,
        session_id=session_id,
        image_path=image_path
    ):
        # Apply output sanitization
        clean = pm.sanitize_response(chunk, user)
        yield clean
        full_response += clean

    # 5. Finalize
    if full_response:
        database.save_message("marin", "user", prompt, user_id=user_id, session_id=session_id)
        database.save_message("marin", "assistant", full_response, user_id=user_id, session_id=session_id)

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
