import os
import json
from pathlib import Path

# Stub for the RAG system to be integrated with the main RAG server later
LEADER_DB_PATH = Path(os.path.dirname(os.path.abspath(__file__))) / "leaders_db.json"

def _init_db():
    if not LEADER_DB_PATH.exists():
        db = {
            "Jerome Powell": {
                "name": "Jerome Powell",
                "role": "Chair, Federal Reserve",
                "country": "United States",
                "personality": "cautious, data-dependent, hawkish leanings",
                "key_policies": ["inflation targeting", "full employment mandate"],
                "market_impact_history": [
                    {
                        "date": "2024-03-20",
                        "event": "FOMC rate decision",
                        "statement_summary": "Held rates steady, signaled 3 cuts in 2024",
                        "market_reaction": "S&P 500 +1.2%, BTC +4.5%, Gold +0.8%",
                        "sentiment_shift": "dovish_pivot"
                    }
                ],
                "trigger_phrases": {
                    "hawkish": ["restrictive", "higher for longer", "inflation risk", "tightening"],
                    "dovish": ["accommodative", "supportive", "rate cuts", "balanced risk"],
                    "neutral": ["data dependent", "meeting by meeting", "appropriate"]
                }
            }
        }
        with open(LEADER_DB_PATH, 'w') as f:
            json.dump(db, f, indent=4)

def query_leader(name: str) -> dict:
    _init_db()
    with open(LEADER_DB_PATH, 'r') as f:
        db = json.load(f)
        
    for leader_name, data in db.items():
        if name.lower() in leader_name.lower():
            return data
    return {}

def analyze_statement(leader_name: str, statement: str) -> dict:
    profile = query_leader(leader_name)
    if not profile:
        return {"error": "Leader not found"}
        
    hawkish_hits = sum(1 for phrase in profile["trigger_phrases"]["hawkish"] if phrase in statement.lower())
    dovish_hits = sum(1 for phrase in profile["trigger_phrases"]["dovish"] if phrase in statement.lower())
    
    sentiment = "neutral"
    if hawkish_hits > dovish_hits: sentiment = "hawkish"
    elif dovish_hits > hawkish_hits: sentiment = "dovish"
    
    return {
        "leader": profile["name"],
        "sentiment": sentiment,
        "hawkish_hits": hawkish_hits,
        "dovish_hits": dovish_hits
    }
