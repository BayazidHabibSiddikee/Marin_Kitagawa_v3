#!/usr/bin/env python3
"""
Portfolio Tracker — Tracks crypto and stock holdings for users.
Integrated with database.py and binance_client.py.
"""

from typing import Dict, Any, List
from tools.binance_client import BinanceManager
from database import get_trades

class PortfolioTracker:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.binance = BinanceManager(user_id)

    def get_summary(self) -> Dict[str, Any]:
        """Combine Binance balances and trade history for a summary."""
        summary = {
            "user_id": self.user_id,
            "crypto_holdings": [],
            "recent_trades": [],
            "status": "connected" if self.binance.is_connected() else "no_keys"
        }
        
        if self.binance.is_connected():
            bal = self.binance.get_balance()
            if bal["ok"]:
                summary["crypto_holdings"] = bal["balances"]
        
        summary["recent_trades"] = get_trades(self.user_id, limit=5)
        
        return summary

    def format_summary(self) -> str:
        s = self.get_summary()
        if s["status"] == "no_keys":
            return "No Binance API keys configured. I can only track your manual trade logs."
        
        lines = [f"📊 Portfolio Summary for {self.user_id}:"]
        
        if s["crypto_holdings"]:
            lines.append("\n💰 Crypto Balances:")
            for b in s["crypto_holdings"]:
                lines.append(f"  - {b['asset']}: {b['free']} (Free) | {b['locked']} (Locked)")
        
        if s["recent_trades"]:
            lines.append("\n📜 Recent Trades:")
            for t in s["recent_trades"]:
                lines.append(f"  - {t['timestamp']}: {t['side'].upper()} {t['amount']} {t['symbol']} @ ${t['price']}")
                
        return "\n".join(lines)

if __name__ == "__main__":
    tracker = PortfolioTracker("USR-MASTER")
    print(tracker.format_summary())
