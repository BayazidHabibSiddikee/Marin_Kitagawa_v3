from duckduckgo_search import DDGS
from tools.agents.business_agents.leader_rag import query_leader, analyze_statement
from tools.agents.business_agents.event_db import query_historical_patterns
import re

def analyze(query: str, symbol: str) -> dict:
    """Geopolitical Agent Analysis ('The Spy')"""
    
    # 1. Gather Intelligence
    news_titles = []
    try:
        with DDGS() as ddgs:
            # Search for broad market sentiment + specific query
            search_term = f"market impact {query} {symbol}"
            results = list(ddgs.news(search_term, max_results=5))
            news_titles = [r['title'] for r in results]
    except Exception:
        pass
        
    # 2. Extract Leader context if applicable
    # Check if any known leaders are mentioned in the query or news
    target_leader = "Jerome Powell" # Default for macro
    for leader in ["Powell", "Biden", "Trump", "Xi Jinping", "Putin"]:
        if leader.lower() in query.lower() or any(leader.lower() in t.lower() for t in news_titles):
            target_leader = leader
            break

    leader_info = query_leader(target_leader)
    sentiment = "neutral"
    historical = []
    
    if leader_info:
        # Analyze current "statement" (composed of news titles)
        statement = " ".join(news_titles)
        analysis = analyze_statement(leader_info["name"], statement)
        sentiment = analysis.get("sentiment", "neutral")
        historical = query_historical_patterns(leader_info["name"], sentiment)
        
    # 3. Formulate Argument
    signal = "HOLD"
    confidence = 0.5
    reasoning = f"Geopolitical environment for {query} is currently stable/neutral."
    
    # Heuristic reasoning
    if sentiment == "hawkish" or any(re.search(r'\b(war|conflict|sanction|crash|drop)\b', t.lower()) for t in news_titles):
        signal = "BEARISH"
        confidence = 0.75
        reasoning = f"Hawkish signals from {target_leader} and negative news flow suggest risk-off sentiment."
    elif sentiment == "dovish" or any(re.search(r'\b(stimulus|growth|recovery|deal|surge)\b', t.lower()) for t in news_titles):
        signal = "BULLISH"
        confidence = 0.75
        reasoning = f"Dovish posture from {target_leader} and positive news headlines suggest risk-on environment."

    return {
        "agent": "geopolitical",
        "signal": signal,
        "confidence": confidence,
        "reasoning": reasoning,
        "evidence": {
            "news_headlines": news_titles[:3],
            "primary_leader": leader_info.get("name", "Unknown"),
            "sentiment_shift": sentiment,
            "historical_correlation": historical
        }
    }
