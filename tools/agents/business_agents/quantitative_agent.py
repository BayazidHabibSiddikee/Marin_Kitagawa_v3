import json
from tools.binance_client import BinanceManager
from tools.technical_analysis import TechnicalAnalyzer
from tools.risk_manager import RiskManager

def analyze(symbol: str, user_id: str) -> dict:
    """Quantitative Agent Analysis ('The Mathematician')"""
    mgr = BinanceManager(user_id)
    
    # 1. Gather Data (Mocked price history for demonstration)
    # In a real app, you would fetch OHLCV from Binance here
    price_res = mgr.get_symbol_price(symbol)
    current_price = float(price_res.get("price", 60000.0)) if price_res.get("ok") else 60000.0
    
    # Generate mock prices for analysis (in production, use real OHLCV data)
    import numpy as np
    mock_prices = [current_price * (1 + (np.random.random() * 0.05 - 0.025)) for _ in range(100)]
    
    # 2. Calculate Indicators
    analyzer = TechnicalAnalyzer(mock_prices)
    analysis = analyzer.full_analysis()
    
    # 3. Risk Assessment
    risk_stats = RiskManager.check_portfolio_risk(user_id, current_price * 0.1) # Check 10% buy
    kelly = RiskManager.kelly_criterion(0.55, 1.5)

    return {
        "agent": "quantitative",
        "signal": analysis["recommendation"],
        "confidence": min(0.9, abs(analysis["signal_score"]) / 5.0),
        "reasoning": f"Trend is {analysis['trend']}. {analysis['recommendation']} signal based on technical score of {analysis['signal_score']}.",
        "indicators": {
            "rsi": analysis["rsi"],
            "macd": analysis["macd"]["crossover"],
            "bollinger": analysis["bollinger"]["position"],
            "current_price": current_price
        },
        "risk": {
            "kelly_suggestion": f"{kelly*100:.1f}% max allocation",
            "portfolio_safety": "SAFE" if risk_stats["is_safe"] else "WARNING",
            "warnings": risk_stats["warnings"]
        }
    }
