#!/usr/bin/env python3
"""
Technical Analysis Engine — calculates RSI, MACD, Bollinger Bands, etc.
Used by the Quantitative Analysis Agent ('The Mathematician').
"""

import pandas as pd
import numpy as np

class TechnicalAnalyzer:
    def __init__(self, prices: list):
        self.df = pd.DataFrame(prices, columns=['close'])

    def rsi(self, period: int = 14) -> float:
        delta = self.df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]

    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
        exp1 = self.df['close'].ewm(span=fast, adjust=False).mean()
        exp2 = self.df['close'].ewm(span=slow, adjust=False).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        hist = macd - signal_line
        return {
            "macd": macd.iloc[-1],
            "signal": signal_line.iloc[-1],
            "histogram": hist.iloc[-1],
            "crossover": "bullish" if hist.iloc[-1] > 0 and hist.iloc[-2] <= 0 else 
                         "bearish" if hist.iloc[-1] < 0 and hist.iloc[-2] >= 0 else "neutral"
        }

    def bollinger_bands(self, period: int = 20, std: int = 2) -> dict:
        sma = self.df['close'].rolling(window=period).mean()
        rstd = self.df['close'].rolling(window=period).std()
        upper = sma + (rstd * std)
        lower = sma - (rstd * std)
        current = self.df['close'].iloc[-1]
        
        position = "middle"
        if current >= upper.iloc[-1]: position = "upper_band"
        elif current <= lower.iloc[-1]: position = "lower_band"
        
        return {
            "upper": upper.iloc[-1],
            "middle": sma.iloc[-1],
            "lower": lower.iloc[-1],
            "position": position
        }

    def ema(self, period: int = 20) -> float:
        return self.df['close'].ewm(span=period, adjust=False).mean().iloc[-1]

    def support_resistance(self, period: int = 20) -> dict:
        return {
            "support": self.df['close'].rolling(window=period).min().iloc[-1],
            "resistance": self.df['close'].rolling(window=period).max().iloc[-1]
        }

    def atr(self, high: list, low: list, period: int = 14) -> float:
        # Simplified ATR using close prices if high/low not available
        tr = np.maximum(np.array(high) - np.array(low), 
                        np.maximum(np.abs(np.array(high) - np.roll(self.df['close'], 1)), 
                                   np.abs(np.array(low) - np.roll(self.df['close'], 1))))
        return pd.Series(tr).rolling(window=period).mean().iloc[-1]

    def full_analysis(self) -> dict:
        curr_price = self.df['close'].iloc[-1]
        rsi_val = self.rsi()
        macd_data = self.macd()
        bb = self.bollinger_bands()
        levels = self.support_resistance()
        
        # Simple scoring
        score = 0
        if rsi_val < 30: score += 2  # oversold
        if rsi_val > 70: score -= 2  # overbought
        if macd_data["crossover"] == "bullish": score += 2
        if macd_data["crossover"] == "bearish": score -= 2
        if bb["position"] == "lower_band": score += 1
        if bb["position"] == "upper_band": score -= 1
        
        trend = "bullish" if curr_price > self.ema(50) else "bearish"
        
        return {
            "price": curr_price,
            "rsi": round(rsi_val, 2),
            "macd": macd_data,
            "bollinger": bb,
            "levels": levels,
            "trend": trend,
            "signal_score": score,
            "recommendation": "BUY" if score >= 3 else "SELL" if score <= -3 else "HOLD"
        }

if __name__ == "__main__":
    # Test with random data
    prices = [60000 + (np.random.random() * 1000) for _ in range(100)]
    analyzer = TechnicalAnalyzer(prices)
    print(json.dumps(analyzer.full_analysis(), indent=2))
