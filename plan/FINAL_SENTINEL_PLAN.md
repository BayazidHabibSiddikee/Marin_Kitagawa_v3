# Marin Tools — The Final Ascent Plan

This document replaces all previous architecture and roadmap files. It outlines the immediate corrective actions and the final state of the Marin HS-02 system.

## 🎯 Current Objectives (High Priority)

### 1. Fix the "Hanging Chat" (LLM Connection)
- **Problem**: Marin takes 10+ minutes to respond or fails with a 503 error.
- **Cause**: The Proxy AI server (`~/.proxy_ai`) attempts to use OpenRouter for local models, which causes a streaming fallback loop that fails. Additionally, Docker networking (`host.docker.internal`) is intermittent.
- **Fix**: 
    - Patch `unified_llm_proxy.py` to skip OpenRouter logic if the model name is local (e.g., `qwen`).
    - Force the `langgraph_agent.py` to route all traffic through the Proxy AI at `http://host.docker.internal:8005/v1` to bridge the Docker/Host gap.

### 2. Restore the "Classic Soul" (UI & Sound)
- **Problem**: The new UI was rejected; user prefers the old avatar-centric look and sound.
- **Fix**: 
    - Re-applied the original `marin_chat.html` from backup.
    - Map `/dev/snd` into the Docker container via `docker-compose.yml` to enable **Piper TTS**.
    - Implement the backend logic to trigger `utils/tts.py`'s `speak_female()` only when the `VOICE_ENABLED` toggle is flipped in the UI.

### 3. Stabilize the Web Core
- **Problem**: "Unhashable type: dict" and "AssertionError" crashes in `main.py`.
- **Cause**: Middleware race conditions and Jinja2 template signature mismatches in newer FastAPI versions.
- **Fix**: 
    - Use strict positional/keyword arguments in `templates.TemplateResponse`.
    - Simplified authentication to **Auto-Login (Bayazid)** to eliminate session-middleware loops, while keeping the **SystemGuard Password Challenge** for security.

## 🛠️ The Three Pillars (Marin Tools)

1. **CHAT**: Integrated study workflow (autonomously finds books/creates roadmaps).
2. **TOOLS**: Technical utility hub (YouTube downloader, PDF analyzer, Research hub, Task mission board).
3. **BUSINESS**: Multi-agent trading arena (The Spy vs. The Mathematician) with dedicated Docker trading nodes.

## 🏹 System State & Cleanup
- All dead side-projects (`archive/`, `minigent/`, etc.) remain deleted.
- Uncensored models (`dolphin-phi2`) have been removed from Git history.
- Repository is lean and focused on production reliability.

---
**Status**: Applying final proxy patches and sound card connectivity.
