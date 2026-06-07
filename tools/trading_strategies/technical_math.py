from tools.trading_strategies.base_strategy import TradingStrategy
from tools.technical_analysis import TechnicalAnalyzer
from tools.risk_manager import RiskManager
import numpy as np

class TechnicalMathematician(TradingStrategy):
    """'The Mathematician' Agent — Technical indicators and risk metrics."""

    def analyze(self, symbol: str, query: str, user_id: str) -> dict:
        # Mock data (to be replaced with live Binance fetch)
        mock_prices = [60000 * (1 + (np.random.random() * 0.04 - 0.02)) for _ in range(100)]
        
        analyzer = TechnicalAnalyzer(mock_prices)
        tech = analyzer.full_analysis()
        
        kelly = RiskManager.kelly_criterion(0.58, 2.0)
        
        return {
            "agent": "Mathematician",
            "signal": tech["recommendation"],
            "confidence": 0.8,
            "reasoning": f"Indicators suggest {tech['recommendation']} based on RSI({tech['rsi']}) and {tech['trend']} trend.",
            "metadata": {"kelly": kelly, "rsi": tech["rsi"]}
        }
