import re

# Import all tools from langgraph_agent to ensure we have the complete list
try:
    from langgraph_agent import ALL_TOOLS
    ALL_TOOL_NAMES = [t.name for t in ALL_TOOLS]
except ImportError:
    # Fallback if langgraph_agent not available yet
    ALL_TOOL_NAMES = []

TOOL_DOMAINS = {
    "Finance-data": {
        "keywords": ["crypto", "bitcoin", "ethereum", "solana", "price", "market", "stock", "share", "equity", "company", "aapl", "tsla", "nvda", "finance"],
        "tools": ["crypto_tool", "stock_tool"]
    },
    "Finance-trading": {
        "keywords": ["trade", "buy", "sell", "portfolio", "binance", "arena", "judge", "business"],
        "tools": ["business_analysis_tool", "binance_tool"]
    },
    "Media": {
        "keywords": ["youtube", "yt", "video", "videos", "watch", "song", "music", "play", "news", "headlines", "world", "latest", "dance", "dancing", "twerk", "boogie", "groove"],
        "tools": ["youtube_search_tool", "youtube_transcript_tool", "news_tool"]
    },
    "Communication": {
        "keywords": ["telegram", "tg", "message", "notify", "notification", "ping", "send message",
                     "email", "mail", "gmail", "send email", "send mail", "write email",
                     "inbox", "compose", "recipient"],
        "tools": ["telegram_tool", "email_tool"]
    },
    "Memory": {
        "keywords": ["remember", "recall", "forget", "memory", "note", "notes", "memorize",
                     "don't forget", "keep in mind", "store this", "save this", "what do you know",
                     "what did i tell", "my preferences", "my goals", "about me"],
        "tools": ["memory_tool"]
    },
    "System": {
        "keywords": ["ls", "list", "show", "check", "scan", "file", "files", "folder", "save", "write", "directory", "cwd", "read", "open", "cat", "analyze", "view", "terminal", "bash", "shell", "run", "execute"],
        "tools": ["terminal_tool", "file_tool", "batch_convert_tool"]
    },
    "Research": {
        "keywords": ["pdf", "document", "paper", "analyzer", "search", "web", "rag", "knowledge", "hub", "scrape", "resource"],
        "tools": ["rag_search", "resource_tool", "pdf_analyze_tool"]
    },
    "Productivity": {
        "keywords": ["timer", "countdown", "stopwatch", "alarm", "wake", "remind", "weather", "temp", "humidity", "rain", "sun", "map", "location", "places", "find", "pin", "habit", "habits", "todo", "task"],
        "tools": ["timer_tool", "alarm_tool", "weather_tool", "map_tool", "habit_tool"]
    },
    "Games": {
        "keywords": ["game", "play", "tictactoe", "widget", "playground", "interactive"],
        "tools": ["playground_tool"]
    },
    "Maths": {
        "keywords": ["plot", "draw", "graph", "math", "equation", "calculate", "algebra", "calculus"],
        "tools": ["math_plot_tool"]
    },
    "Study": {
        "keywords": ["learn", "teach", "study", "master", "expert", "tutorial", "how to", "course", "book", "textbook", "epub", "novel", "guide", "manual", "python", "arduino", "coding", "programming"],
        "tools": ["learn_topic_tool", "book_download_tool"]
    }
}

# Cross-domain requests are common ("get the transcript and save it to a file"),
# so expose the union of the top-scoring domains instead of a single winner —
# capped so the strategist never sees an unmanageable tool list.
MAX_DOMAINS = 3
MAX_TOOLS = 12

def get_relevant_tools(query: str, threshold: float = 0.3) -> list[str]:
    """
    Level 1 Router: Classifies the query into tool domains using zero-latency keyword mapping.
    This replaces the FAISS embeddings (which fail when Ollama/HuggingFace are unreachable) and is
    incredibly robust for small model classification pipelines.
    Returns the union of the top MAX_DOMAINS matching domains' tools (capped at MAX_TOOLS),
    or an empty list if nothing matches so the strategist answers directly.
    """
    lower_query = query.lower()

    scored = []
    for domain, data in TOOL_DOMAINS.items():
        score = sum(1 for kw in data["keywords"] if re.search(r'\b' + re.escape(kw) + r'\b', lower_query))
        if score > 0:
            scored.append((score, domain))

    if not scored:
        print("[SemanticRouter] No domain matched. Returning empty tools list to force clarification.")
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    tools: list[str] = []
    picked = []
    for score, domain in scored[:MAX_DOMAINS]:
        picked.append(f"{domain}({score})")
        for t in TOOL_DOMAINS[domain]["tools"]:
            if t not in tools and len(tools) < MAX_TOOLS:
                tools.append(t)

    print(f"[SemanticRouter] Matched domains: {', '.join(picked)} -> {len(tools)} tools")
    return tools
