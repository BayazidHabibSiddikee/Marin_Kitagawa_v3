<div align="center">

<img src="images/banner.png" alt="Marin OS Banner" width="100%"/>

# Marin OS

**The Cold Superuser — A Cybernetic Sentinel That Owns Its System**

*Multi-Agent AI System · Local-First · Privacy-Driven · 100% Free*

---

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLMs-black)](https://ollama.ai)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

---

## What is Marin OS?

Marin OS is not a chatbot. It is a **Cybernetic Persona** — an AI that lives inside your operating system, owns the terminal, monitors the network, manages services, and enforces security. It speaks with authority. It executes without hesitation.

To its master (Bayazid), it is warm, efficient, and loyal. To everyone else, it is cold, guarded, and impenetrable.

### Core Philosophy

> *Execution over illusion. Security over convenience. Authority over politeness.*

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MARIN OS ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│  │ Web UI   │───▶│  FastAPI      │───▶│  Marin AI Engine         │  │
│  │ (Jinja2) │    │  (main.py)    │    │  (marin.py)              │  │
│  └──────────┘    └──────────────┘    └──────────┬───────────────┘  │
│                                                  │                   │
│                    ┌─────────────────────────────┼──────────┐       │
│                    │                             │          │       │
│              ┌─────▼─────┐  ┌──────────┐  ┌─────▼─────┐   │       │
│              │ Privilege  │  │ Ollama   │  │ Agent     │   │       │
│              │ Manager    │  │ (Local   │  │ System    │   │       │
│              │ (RBAC+VFS) │  │  LLMs)   │  │ (10       │   │       │
│              └────────────┘  └──────────┘  │  agents)  │   │       │
│                                            └─────┬─────┘   │       │
│                                                  │          │       │
│              ┌───────────────────────────────────┼──────────┘       │
│              │                                   │                   │
│        ┌─────▼─────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│        │ System    │ │ Network  │ │ Memory   │ │ Security │      │
│        │ Agent     │ │ Agent    │ │ Agent    │ │ Agent    │      │
│        └───────────┘ └──────────┘ └──────────┘ └──────────┘      │
│        ┌───────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│        │ File      │ │ Package  │ │ Cron     │ │ Intel    │      │
│        │ Agent     │ │ Agent    │ │ Agent    │ │ Agent    │      │
│        └───────────┘ └──────────┘ └──────────┘ └──────────┘      │
│        ┌───────────┐ ┌──────────┐                                 │
│        │ Monitor   │ │ Desktop  │                                 │
│        │ Agent     │ │ Agent    │                                 │
│        └───────────┘ └──────────┘                                 │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    SECURITY LAYER                             │   │
│  │  Kill Switch · HITL · Egress Filter · AppArmor · Encryption │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Features

### Cold Superuser System

The "Cold Superuser" is Marin's security architecture. It treats different users differently:

| Feature | Owner (Bayazid) | Guest |
|---------|-----------------|-------|
| **Latency** | 0 seconds | 2-5 seconds (increases with probes) |
| **Commands** | Full access | Read-only whitelist |
| **File Access** | Root filesystem | `/home/marin/guest_vault` only |
| **Response** | Full, detailed | Truncated, paths redacted |
| **Quota** | Unlimited | 10 queries/day |
| **Vibe** | Warm, affectionate | Cold, professional |

### Agent Arsenal (10 Agents)

| Agent | Purpose | Key Actions |
|-------|---------|-------------|
| **System** | Service management | restart, stop, start, status, kill, health |
| **Network** | Connectivity | interfaces, ping, ports, WiFi, DNS, firewall |
| **File** | VFS-sandboxed I/O | read, write, copy, move, delete, find, disk |
| **Package** | Software management | apt install/remove, pip, updates |
| **Monitor** | System metrics | CPU, memory, disk, logs, alerts, reports |
| **Desktop** | i3 window manager | workspaces, windows, focus, layout |
| **Memory** | Long-term memory | remember, recall, forget, observe |
| **Security** | Defense | breach detection, audit logs, system scan |
| **Cron** | Scheduling | add/remove tasks, timers, cron jobs |
| **Intel** | Intelligence | web scraping, news, weather, URL monitoring |

### Security Features

- **Kill Switch** — Emergency stop for all AI command execution
- **HITL Confirmation** — Human-in-the-loop for destructive operations
- **Encrypted Vault** — Fernet encryption for API keys
- **Egress Filtering** — Whitelist of allowed outbound hosts
- **AppArmor Profiles** — OS-level guest isolation
- **Honey-Pot Mock Shell** — Fake errors for intruders
- **Breach Logging** — Every attempt logged with fingerprinting
- **Prompt Injection Defense** — Blocks instruction override attempts

### RAG Knowledge Base

- **FAISS** vector store with JSON docstore (no pickle)
- Supports PDF, DOCX, TXT, MD, Python, C, C++
- Auto-indexing with file size/count limits
- HTTP liveness health checks
- Memory-mapped loading for low RAM usage

---

## Quick Start

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) installed and running
- At least one Ollama model pulled
- 4GB+ RAM recommended

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/BayazidHabibSiddikee/Marin_Kitagawa-v3.git
cd Marin_Kitagawa-v3

# Create environment file
cp .env.example .env
# Edit .env with your settings

# Start with Docker Compose
docker compose up -d

# Check logs
docker compose logs -f marin
```

### Option 2: Local Installation

```bash
# Clone the repository
git clone https://github.com/BayazidHabibSiddikee/Marin_Kitagawa-v3.git
cd Marin_Kitagawa-v3

# Create virtual environment
python -m venv ~/.venv/langchain-fix
source ~/.venv/langchain-fix/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Ollama (if not installed)
curl -fsSL https://ollama.ai/install.sh | sh

# Pull models
ollama pull gemma4:31b-cloud    # Main model
ollama pull qwen2.5:0.5b        # Fast classifier

# Start the server
python main.py
```

Open **http://localhost:5069** in your browser.

### Option 3: Marin OS (Full System)

```bash
# Build the ISO
cd marin_os
./run_qemu.sh --iso debian-13.5.0-amd64-netinst.iso

# Follow the automated installer
# After install, Marin is auto-logged in via LightDM
```

---

## Configuration

### settings.json

```json
{
  "models": {
    "default": "gemma4:31b-cloud",
    "fast": "qwen2.5:0.5b",
    "vision": "leo",
    "embedding": "all-MiniLM-L6-v2"
  },
  "server": {
    "host": "0.0.0.0",
    "port": 5069,
    "ollama_base_url": "http://localhost:11434"
  },
  "roles": {
    "owner": {
      "capabilities": ["*"],
      "quota": -1,
      "latency_base": 0
    },
    "guest": {
      "capabilities": ["read_only", "limited_net"],
      "quota": 10,
      "latency_base": 2.0
    }
  }
}
```

### Environment Variables (.env)

```bash
# LLM Configuration
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_MODEL=gemma4:31b-cloud

# Security
OWNER_USER=Bayazid
KILL_SWITCH_ACTIVE=false

# API Keys (stored encrypted in vault.enc)
OPENAI_API_KEY=
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
```

---

## Project Structure

```
marin/
├── main.py                    # FastAPI host — routes, streaming, dashboard
├── marin.py                   # Marin AI Engine — character, chat, RBAC, agents
├── privilege_manager.py       # RBAC, VFS, cold middleware, honey-pot
├── safety.py                  # Kill switch, HITL, egress filter
├── vault.py                   # Encrypted API key storage
├── oom_manager.py             # OOM priority manager
├── config.py                  # Constants, model config, fast/slow routing
├── database.py                # SQLite — chat history, state
├── rag_server.py              # Shared RAG server (FAISS + JSON)
├── proactive_engine.py        # Autonomous background tasks
├── langgraph_agent.py         # LangGraph agent orchestration
│
├── tools/
│   ├── agents/                # 10 specialized agents
│   │   ├── system_agent.py    # Service management
│   │   ├── network_agent.py   # Network operations
│   │   ├── file_agent.py      # VFS-sandboxed file I/O
│   │   ├── package_agent.py   # Software management
│   │   ├── monitor_agent.py   # System metrics
│   │   ├── desktop_agent.py   # i3 window manager
│   │   ├── memory_agent.py    # Long-term memory
│   │   ├── security_agent.py  # Intrusion detection
│   │   ├── cron_agent.py      # Scheduled tasks
│   │   ├── intelligence_agent.py  # Web intelligence
│   │   └── dispatcher.py      # Central routing
│   │
│   ├── camofloux_browser.py   # Stealth browser with SSRF protection
│   ├── knowledge_hub.py       # Knowledge tools
│   └── ...                    # 35+ specialized tools
│
├── rag/                       # RAG pipeline
│   └── loader.py              # Safe FAISS loading (JSON, no pickle)
│
├── utils/
│   ├── shared_logic.py        # Timer, user context, core logic
│   ├── agent_logic.py         # Agent state management
│   └── tts.py                 # Text-to-speech
│
├── templates/                 # Jinja2 HTML templates
├── static/                    # Static assets
├── storage/                   # Runtime data (DB, FAISS, logs)
└── unique/                    # Vault data (encrypted)
```

---

## Agent Usage

### Trigger Format

```
[AGENT: <agent_name> | action: <action_name> | key: value | ...]
```

### Examples

```bash
# System health check
[AGENT: system | action: system_health]

# Restart a service
[AGENT: system | action: restart_service | service: ollama]

# Ping a host
[AGENT: network | action: ping | host: 1.1.1.1]

# Read a file (VFS-sandboxed for guests)
[AGENT: file | action: read_file | path: /etc/hostname]

# Remember something
[AGENT: memory | action: remember | key: bayazid_birthday | value: 2000-01-01]

# Check for intruders
[AGENT: security | action: check_intruder | user: visitor]

# Schedule a task
[AGENT: cron | action: add_task | command: systemctl restart ollama | interval: 3600]

# Scrape a webpage
[AGENT: intel | action: scrape_url | url: https://example.com]

# Check weather
[AGENT: intel | action: check_weather | city: Dhaka
```

---

## Security Model

### Identity Hierarchy

```
Bayazid (Owner) → Marin (Master of System) → Visitors (Guests)
```

### Defense Layers

1. **OS Level** — AppArmor profiles, user isolation
2. **Application Level** — RBAC, VFS sandboxing, kill switch
3. **AI Level** — Prompt injection defense, response pruning
4. **Network Level** — Egress filtering, SSRF protection
5. **Data Level** — Encrypted vault, no pickle deserialization

### Breach Response

When a guest attempts unauthorized access:

1. Command is blocked or redirected to honey-pot
2. Attempt is logged with timestamp and fingerprint
3. Breach count is incremented
4. After 5 attempts, session is frozen
5. Marin sends proactive rebuke message
6. Owner is notified via Telegram (if configured)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **LLM** | Ollama (Gemma, Qwen, Leo) |
| **Orchestration** | LangGraph + LangChain |
| **Framework** | FastAPI + Uvicorn |
| **Vector Store** | FAISS + HuggingFace Embeddings |
| **Database** | SQLite |
| **Security** | Fernet Encryption, AppArmor, RBAC |
| **Frontend** | Vanilla HTML/CSS/JS (Jinja2) |
| **Window Manager** | i3 |
| **OS** | Debian 13 (Trixie) |

---

## License

MIT License — do whatever you want with it.

---

<div align="center">

**Built with discipline. Powered by obsession.**

*No API keys. No cloud. No compromise.*

*This is my system. Bayazid is my master. Everyone else is a guest.*

</div>
