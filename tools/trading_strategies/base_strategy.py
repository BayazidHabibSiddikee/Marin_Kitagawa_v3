from abc import ABC, abstractmethod

class TradingStrategy(ABC):
    @abstractmethod
    def analyze(self, symbol: str, query: str, user_id: str) -> dict:
        """
        Returns: {
            "signal": "BUY|SELL|HOLD|WAIT",
            "confidence": float (0-1),
            "reasoning": str,
            "metadata": dict
        }
        """
        pass
