# Marin OS Architecture — The SwordFish Era

## 1. Design Philosophy
- **Tool-First**: Every user capability is defined as a discrete tool.
- **Unified Brain**: A single intent classifier (`marin_fier.py`) routing to a single orchestrator (`langgraph_agent.py`).
- **Production-Grade**: Secure by default, user-isolated, and supervised by `supervisord`.

## 2. The Core Pipeline (One Brain)
1. **User Input** → `utils/agent_logic.py:stream_marin_chat()`
2. **Intent Classification** → `marin_fier.py` (Regex-First, LLM-Second fallback)
3. **Context Enrichment** → RAG context, Media analysis (YouTube/Image), Live market data.
4. **Agent Orchestration** → `langgraph_agent.py` (LangGraph 4-node cycle)
5. **Verified Execution** → Tools executed in a Docker sandbox or safe environment.
6. **Persona Delivery** → Final response wrapped in Marin's personality.

## 3. Tool Registry
All tools are defined in `langgraph_agent.py` using the `@tool` decorator.
`marin_fier.py` imports this registry to ensure zero drift between the classifier and the executor.

## 4. Security
- **RBAC**: Handled by `privilege_manager.py`. Owners have full access; guests have whitelisted tool access and progressive latency.
- **Sandbox**: All shell commands run via `utils/command_runner.py` which delegates to a Docker container on the host.
- **Auth**: Multi-user support with Google OAuth and per-user API keys.

## 5. Deployment
- **Container**: `docker-compose.yml` with bridge networking and resource limits.
- **Process Supervisor**: `supervisord` ensures RAG, ModuleFlow, and the Main App are always running.
