import os
import re
import json
from pathlib import Path

def analyze_brain():
    """Build a graph of Marin's cognitive architecture for Marin Tools Era."""
    nodes = [
        {"id": "user", "label": "User Input", "type": "input"},
        {"id": "classifier", "label": "Regex/LLM Classifier", "type": "brain"},
        {"id": "strategist", "label": "LangGraph Strategist", "type": "brain"},
        {"id": "executor", "label": "Multi-Agent Executor", "type": "brain"},
        {"id": "auditor", "label": "Security Auditor", "type": "brain"},
        {"id": "persona", "label": "Marin Persona", "type": "brain"},
        {"id": "arena", "label": "Trading Arena", "type": "business"},
        {"id": "spy", "label": "The Spy (Geo)", "type": "agent"},
        {"id": "math", "label": "The Math (Quant)", "type": "agent"},
        {"id": "trading_node", "label": "Trading Node (Docker)", "type": "docker"}
    ]
    
    links = [
        {"source": "user", "target": "classifier"},
        {"source": "classifier", "target": "strategist"},
        {"source": "strategist", "target": "executor"},
        {"source": "executor", "target": "auditor"},
        {"source": "auditor", "target": "persona"},
        {"source": "auditor", "target": "executor", "label": "Correction"},
        {"source": "persona", "target": "user"},
        {"source": "executor", "target": "arena", "label": "Business Logic"},
        {"source": "arena", "target": "spy"},
        {"source": "arena", "target": "math"},
        {"source": "arena", "target": "trading_node", "label": "Control"},
        {"source": "trading_node", "target": "arena", "label": "Execution"}
    ]
    
    # Dynamically scan tools from langgraph_agent.py
    try:
        with open("langgraph_agent.py", "r") as f:
            content = f.read()
            tools = re.findall(r'@tool\s+def (\w+)', content)
            for t in tools:
                if t in ("business_analysis_tool", "binance_tool", "execute_trade_tool"):
                    target = "arena"
                else:
                    target = "executor"
                
                nodes.append({"id": t, "label": t.replace("_", " "), "type": "tool"})
                links.append({"source": target, "target": t})
    except: pass
    
    return {"nodes": nodes, "links": links}

if __name__ == "__main__":
    graph = analyze_brain()
    # Ensure dir exists
    os.makedirs("moduleflow", exist_ok=True)
    with open("moduleflow/graph.json", "w") as f:
        json.dump(graph, f, indent=4)
    print("Marin Brain Map updated: moduleflow/graph.json")
