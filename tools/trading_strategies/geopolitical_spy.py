import re
from tools.trading_strategies.base_strategy import TradingStrategy
from duckduckgo_search import DDGS

def query_leader(name: str) -> dict:
    return {"name": name, "posture": "neutral"}

def analyze_statement(name: str, statement: str) -> dict:
    text = statement.lower()
    if any(x in text for x in ["cut", "dovish", "stimulus", "support"]):
        return {"sentiment": "dovish"}
    if any(x in text for x in ["hike", "hawkish", "inflation", "tighten"]):
        return {"sentiment": "hawkish"}
    return {"sentiment": "neutral"}

class GeopoliticalSpy(TradingStrategy):
    """'The Spy' Agent — News sentiment and leader posture analysis."""
    
    def analyze(self, symbol: str, query: str, user_id: str) -> dict:
        news_titles = []
        try:
            with DDGS() as ddgs:
                results = list(ddgs.news(f"market impact {query} {symbol}", max_results=5))
                news_titles = [r['title'] for r in results]
        except: pass

        # Default to Powell for macro
        leader_info = query_leader("Jerome Powell")
        statement = " ".join(news_titles)
        analysis = analyze_statement(leader_info["name"], statement) if leader_info else {"sentiment": "neutral"}
        
        sentiment = analysis["sentiment"]
        signal = "HOLD"
        conf = 0.6
        
        if sentiment == "hawkish":
            signal, conf = "BEARISH", 0.75
        elif sentiment == "dovish":
            signal, conf = "BULLISH", 0.75

        return {
            "agent": "Spy",
            "signal": signal,
            "confidence": conf,
            "reasoning": f"Macro analysis via {leader_info.get('name', 'General News')} indicates {sentiment} sentiment.",
            "metadata": {"news": news_titles[:2]}
        }
