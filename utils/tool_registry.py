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
    "System": {
        "keywords": ["ls", "list", "show", "check", "scan", "files", "directory", "cwd", "read", "open", "cat", "analyze", "view", "terminal", "bash", "shell", "run", "execute"],
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

def get_relevant_tools(query: str, threshold: float = 0.3) -> list[str]:
    """
    Level 1 Router: Classifies the query into a specific tool domain using zero-latency keyword mapping.
    This replaces the FAISS embeddings (which fail when Ollama/HuggingFace are unreachable) and is
    incredibly robust for small model classification pipelines.
    Returns ALL tools if no domain matches, allowing the strategist to still plan effectively.
    """
    lower_query = query.lower()

    best_domain = None
    best_score = 0

    for domain, data in TOOL_DOMAINS.items():
        score = sum(1 for kw in data["keywords"] if re.search(r'\b' + kw + r'\b', lower_query))
        if score > best_score:
            best_score = score
            best_domain = domain

    if best_score > 0 and best_domain:
        print(f"[SemanticRouter] Matched Domain: {best_domain} (Score: {best_score})")
        return TOOL_DOMAINS[best_domain]["tools"]

    print("[SemanticRouter] No domain matched. Returning empty tools list to force clarification.")
    return []
