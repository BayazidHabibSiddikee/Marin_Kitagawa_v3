import json
from typing import Dict, Any

from tools.agents.business_agents.geopolitical_agent import analyze as geo_analyze
from tools.agents.business_agents.quantitative_agent import analyze as quant_analyze
from tools.agents.business_agents.arena import run_arena_debate
from tools.binance_client import BinanceManager

def run_business_analysis(query: str, symbol: str = "BTCUSDT", user_id: str = "USR-MASTER") -> Dict[str, Any]:
    """The Judge: Orchestrates the business analysis and debate."""
    print(f"[Orchestrator] Running Business Analysis for {symbol} (User: {user_id})")
    
    # 1. Dispatch Sub-Agents
    geo_result = geo_analyze(query, symbol)
    quant_result = quant_analyze(symbol, user_id)
    
    # 2. Run Arena Debate
    debate_result = run_arena_debate(geo_result, quant_result)
    
    # 3. Format Output
    output = {
        "symbol": symbol,
        "query": query,
        "geopolitical_view": geo_result,
        "quantitative_view": quant_result,
        "final_verdict": debate_result
    }
    
    return output

def format_business_report(analysis: Dict[str, Any]) -> str:
    """Formats the analysis dict into a readable report for the LLM/User."""
    verdict = analysis["final_verdict"]
    geo = analysis["geopolitical_view"]
    quant = analysis["quantitative_view"]
    
    report = [
        f"🏛️ THE TRADING ARENA: VERDICT for {analysis['symbol']}",
        "═" * 60,
        f"🎯 FINAL SIGNAL: **{verdict['final_signal']}**",
        f"🛡️ CONFIDENCE: {int(verdict['final_confidence'] * 100)}%",
        f"💡 JUDGE REASONING: {verdict['final_reasoning']}",
        "",
        "─────────────── DEBATE SUB-AGENTS ───────────────",
        f"🕵️ THE SPY (Geopolitical): {geo['signal']} (Conf: {geo['confidence']})",
        f"   - {geo['reasoning']}",
        f"   - News: {', '.join(geo['evidence']['news_headlines'][:2])}...",
        "",
        f"📐 THE MATHEMATICIAN (Quantitative): {quant['signal']} (Conf: {quant['confidence']})",
        f"   - {quant['reasoning']}",
        f"   - Indicators: RSI({quant['indicators']['rsi']}), Bollinger({quant['indicators']['bollinger']})",
        f"   - Risk Assessment: {quant['risk']['kelly_suggestion']} (Status: {quant['risk']['portfolio_safety']})",
        "═" * 60,
        "⚠️ WARNING: This is AI-generated financial analysis. Crypto trading carries high risk."
    ]
    return "\n".join(report)

if __name__ == "__main__":
    res = run_business_analysis("What will happen to BTC if Powell speaks hawkish?", "BTCUSDT")
    print(format_business_report(res))
