#!/usr/bin/env python3
"""
Binance Client Tool — Multi-user Binance API wrapper.
Handles authenticated requests for specific users using encrypted keys.
"""

import os
import json
from typing import Dict, Any, List, Optional
from binance.client import Client
from binance.exceptions import BinanceAPIException
from database import get_user_key
from vault import get_vault

class BinanceManager:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.client = self._get_client()

    def _get_client(self) -> Optional[Client]:
        """Fetch user's Binance keys and return a Client."""
        key_data = get_user_key(self.user_id, "binance")
        if not key_data:
            return None
        
        # In a real app, keys would be encrypted in DB too, 
        # but here we'll assume they are stored raw for simplicity or handled by vault
        api_key = key_data["api_key"]
        api_secret = key_data["api_secret"]
        
        return Client(api_key, api_secret)

    def is_connected(self) -> bool:
        return self.client is not None

    def get_balance(self) -> Dict[str, Any]:
        if not self.client: return {"ok": False, "error": "No Binance keys configured."}
        try:
            account = self.client.get_account()
            balances = [b for b in account['balances'] if float(b['free']) > 0 or float(b['locked']) > 0]
            return {"ok": True, "balances": balances}
        except BinanceAPIException as e:
            return {"ok": False, "error": str(e)}

    def get_symbol_price(self, symbol: str) -> Dict[str, Any]:
        # Prices are public, don't need auth if client is None
        try:
            temp_client = self.client or Client()
            ticker = temp_client.get_symbol_ticker(symbol=symbol)
            return {"ok": True, "price": ticker['price']}
        except BinanceAPIException as e:
            return {"ok": False, "error": str(e)}

    def execute_trade(self, symbol: str, side: str, amount: float, price: float = None) -> Dict[str, Any]:
        if not self.client: return {"ok": False, "error": "No Binance keys configured."}
        try:
            if price:
                # Limit Order
                order = self.client.create_order(
                    symbol=symbol,
                    side=side.upper(),
                    type='LIMIT',
                    timeInForce='GTC',
                    quantity=amount,
                    price=str(price)
                )
            else:
                # Market Order
                order = self.client.create_order(
                    symbol=symbol,
                    side=side.upper(),
                    type='MARKET',
                    quantity=amount
                )
            return {"ok": True, "order": order}
        except BinanceAPIException as e:
            return {"ok": False, "error": str(e)}

    def get_portfolio(self) -> Dict[str, Any]:
        """Fetch total portfolio state."""
        bal = self.get_balance()
        if not bal["ok"]: return bal
        
        # Calculate total USD value
        total_usd = 0.0
        holdings = []
        for b in bal["balances"]:
            asset = b["asset"]
            free = float(b["free"])
            locked = float(b["locked"])
            amount = free + locked
            
            usd_val = 0.0
            if asset == "USDT":
                usd_val = amount
            else:
                price_res = self.get_symbol_price(f"{asset}USDT")
                if price_res["ok"]:
                    usd_val = amount * float(price_res["price"])
            
            total_usd += usd_val
            holdings.append({
                "asset": asset,
                "amount": amount,
                "usd_value": round(usd_val, 2)
            })
            
        return {
            "ok": True,
            "total_usd": round(total_usd, 2),
            "holdings": holdings
        }

    def get_history(self, symbol: str) -> List[Dict[str, Any]]:
        if not self.client: return []
        try:
            return self.client.get_all_orders(symbol=symbol, limit=10)
        except:
            return []

if __name__ == "__main__":
    # Test with a dummy user
    mgr = BinanceManager("USR-MASTER")
    print(mgr.get_symbol_price("BTCUSDT"))
