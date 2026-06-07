#!/usr/bin/env python3
"""
Trade Executor — background service for price alerts and trade execution.
"""

import asyncio
import time
from database import save_trade
from tools.binance_client import BinanceManager

class TradeExecutor:
    def __init__(self):
        self.alerts = [] # List of {"user_id": ..., "symbol": ..., "side": ..., "condition": "below|above", "target": ..., "amount": ...}

    def add_alert(self, user_id: str, symbol: str, side: str, condition: str, target: float, amount: float):
        alert = {
            "user_id": user_id,
            "symbol": symbol,
            "side": side,
            "condition": condition,
            "target": target,
            "amount": amount,
            "status": "active"
        }
        self.alerts.append(alert)
        return f"Set alert: {side} {amount} {symbol} when price is {condition} {target}"

    async def run_loop(self):
        """Background loop to check alerts."""
        print("[TradeExecutor] Background loop started.")
        while True:
            for alert in self.alerts[:]:
                if alert["status"] != "active": continue
                
                # Check price
                mgr = BinanceManager(alert["user_id"])
                res = mgr.get_symbol_price(alert["symbol"])
                
                if res["ok"]:
                    current_price = float(res["price"])
                    triggered = False
                    
                    if alert["condition"] == "below" and current_price <= alert["target"]:
                        triggered = True
                    elif alert["condition"] == "above" and current_price >= alert["target"]:
                        triggered = True
                        
                    if triggered:
                        print(f"[TradeExecutor] TRIGGERED: {alert['side']} {alert['symbol']} at {current_price}")
                        # Execute trade
                        trade_res = mgr.execute_trade(alert["symbol"], alert["side"], alert["amount"])
                        
                        if trade_res["ok"]:
                            save_trade(alert["user_id"], alert["symbol"], alert["side"], alert["amount"], current_price, status='executed', order_id=str(trade_res["order"]["orderId"]))
                            alert["status"] = "triggered"
                            # In a real app, send Telegram here
                        else:
                            save_trade(alert["user_id"], alert["symbol"], alert["side"], alert["amount"], current_price, status='failed')
                            alert["status"] = "failed"
                            
            await asyncio.sleep(60) # Check every minute

# Singleton for runtime (or run as separate process)
executor = TradeExecutor()

if __name__ == "__main__":
    asyncio.run(executor.run_loop())
