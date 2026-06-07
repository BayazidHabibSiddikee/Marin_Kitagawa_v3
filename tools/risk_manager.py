#!/usr/bin/env python3
"""
Risk Management Engine — calculates position sizing, Sharpe ratio, and Value at Risk.
Used by the Quantitative Analysis Agent ('The Mathematician').
"""

import numpy as np

class RiskManager:
    @staticmethod
    def kelly_criterion(win_rate: float, win_loss_ratio: float) -> float:
        """Calculate optimal position size fraction."""
        if win_loss_ratio <= 0: return 0.0
        fraction = win_rate - ((1 - win_rate) / win_loss_ratio)
        return max(0.0, fraction)

    @staticmethod
    def position_size(account_balance: float, risk_per_trade: float, entry: float, stop_loss: float) -> float:
        """Calculate position size based on dollar risk."""
        if entry == stop_loss: return 0.0
        risk_amount = account_balance * risk_per_trade
        size = risk_amount / abs(entry - stop_loss)
        return size

    @staticmethod
    def sharpe_ratio(returns: list, risk_free_rate: float = 0.05) -> float:
        """Calculate Sharpe Ratio for a series of returns."""
        if not returns or len(returns) < 2: return 0.0
        avg_return = np.mean(returns)
        std_return = np.std(returns)
        if std_return == 0: return 0.0
        return (avg_return - (risk_free_rate / 365)) / std_return

    @staticmethod
    def portfolio_value_at_risk(holdings: list, confidence: float = 0.95) -> float:
        """Simple parametric VaR calculation."""
        # Simple implementation: assumes holdings are values
        total_value = sum(holdings)
        # Assuming 5% volatility for crypto daily
        volatility = 0.05 
        z_score = 1.645 if confidence == 0.95 else 2.326 # for 99%
        var = total_value * z_score * volatility
        return var

    @staticmethod
    def check_portfolio_risk(user_id: str, new_trade_value: float) -> dict:
        """Check if a new trade exceeds risk parameters (Mock for now)."""
        # In reality, fetch account balance and current exposure
        mock_balance = 10000.0
        mock_exposure = 4000.0
        
        limit_percent = 0.20 # Max 20% per trade
        exposure_limit = 0.80 # Max 80% total exposure
        
        warnings = []
        if new_trade_value > (mock_balance * limit_percent):
            warnings.append("New trade exceeds 20% of account balance.")
        if (mock_exposure + new_trade_value) > (mock_balance * exposure_limit):
            warnings.append("Total portfolio exposure exceeds 80% limit.")
            
        return {
            "is_safe": len(warnings) == 0,
            "warnings": warnings,
            "current_exposure": mock_exposure,
            "balance": mock_balance
        }

if __name__ == "__main__":
    # Test
    kelly = RiskManager.kelly_criterion(0.60, 2.0)
    print(f"Kelly Suggestion: {kelly*100:.1f}%")
    
    size = RiskManager.position_size(10000, 0.02, 60000, 58000)
    print(f"Trade Size: {size:.4f} BTC")
