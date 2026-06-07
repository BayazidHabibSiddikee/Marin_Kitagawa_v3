from typing import List, Dict, Any
from tools.trading_strategies.geopolitical_spy import GeopoliticalSpy
from tools.trading_strategies.technical_math import TechnicalMathematician

class BusinessJudge:
    """The Judge — Orchestrates the Arena Debate and manages trading nodes."""
    
    def __init__(self):
        self.strategies = [GeopoliticalSpy(), TechnicalMathematician()]

    def run_debate(self, symbol: str, query: str, user_id: str) -> str:
        # Check if trading node is active
        from tools.docker_orchestrator import orchestrator
        nodes = orchestrator.list_containers(all=True)
        is_node_up = any(n["name"] == "marin-trading-node" and n["status"] == "running" for n in nodes)
        
        status_msg = "🟢 Trading Node Active" if is_node_up else "⚪ Trading Node Idle"
        
        results = [s.analyze(symbol, query, user_id) for s in self.strategies]
        
        spy = results[0]
        math = results[1]
        
        report = [
            f"🏛️ **THE MARIN ARENA: {symbol} REPORT**",
            "═" * 50,
            f"🕵️ **SPY VERDICT**: {spy['signal']} (Conf: {spy['confidence']})",
            f"   > {spy['reasoning']}",
            "",
            f"📐 **MATHEMATICIAN VERDICT**: {math['signal']} (Conf: {math['confidence']})",
            f"   > {math['reasoning']}",
            "═" * 50
        ]
        
        # Conflict Resolution
        if spy["signal"] == math["signal"]:
            verdict = spy["signal"]
            final_reasoning = "Unanimous alignment between geopolitical and technical analysis."
        else:
            # Weigh confidence
            if spy["confidence"] > math["confidence"]:
                verdict = spy["signal"]
                final_reasoning = "Geopolitical factors currently outweigh technical indicators."
            else:
                verdict = math["signal"]
                final_reasoning = "Technical price action is overriding geopolitical noise."

        report.append(f"🎯 **FINAL JUDGEMENT**: **{verdict}**")
        report.append(f"💡 **RATIONALE**: {final_reasoning}")
        
        return "\n".join(report)

judge = BusinessJudge()
