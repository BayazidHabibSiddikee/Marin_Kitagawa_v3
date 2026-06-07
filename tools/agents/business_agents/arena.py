import json

def run_arena_debate(geo_arg: dict, quant_arg: dict) -> dict:
    """The Arena Debate between The Spy and The Mathematician.
    
    Round 1: Initial Presentation
    Round 2: Cross-Examination (Weights Confidence)
    Round 3: Final Decision by The Judge
    """
    
    debate_log = []
    debate_log.append({"round": 1, "agent": "geopolitical", "argument": geo_arg["reasoning"]})
    debate_log.append({"round": 1, "agent": "quantitative", "argument": quant_arg["reasoning"]})
    
    # Simple conflict detection
    if geo_arg["signal"] == quant_arg["signal"]:
        final_signal = geo_arg["signal"]
        # Aggregated confidence
        final_confidence = min(0.95, (geo_arg["confidence"] + quant_arg["confidence"]) / 1.5)
        final_reasoning = f"Unanimous verdict: {final_signal}. Total convergence between macro and technical data."
    else:
        # Round 2: The Judge weighs the arguments
        # Heuristic: Geopolitical has priority on macro (FED, War), Quantitative has priority on entry (RSI, BB)
        if "fomc" in geo_arg["reasoning"].lower() or "war" in geo_arg["reasoning"].lower():
            # Geopolitical weight up
            geo_weight = geo_arg["confidence"] * 1.2
            quant_weight = quant_arg["confidence"]
        else:
            geo_weight = geo_arg["confidence"]
            quant_weight = quant_arg["confidence"] * 1.1

        if geo_weight > quant_weight:
            final_signal = geo_arg["signal"]
            final_confidence = geo_arg["confidence"]
            final_reasoning = f"Geopolitical factors are currently dominant. Verdict: {final_signal}."
        else:
            final_signal = quant_arg["signal"]
            final_confidence = quant_arg["confidence"]
            final_reasoning = f"Technical indicators are overriding geopolitical noise. Verdict: {final_signal}."

    return {
        "final_signal": final_signal,
        "final_confidence": round(final_confidence, 2),
        "final_reasoning": final_reasoning,
        "debate_rounds": debate_log
    }
