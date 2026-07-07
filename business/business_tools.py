# business_tools.py — Specialized tools for market analysis and trading.
# Part of the separated business pipeline.


from langchain_core.tools import tool


@tool
def binance_tool(action: str, symbol: str = "BTCUSDT", amount: float = None, price: float = None, user_id: str = "USR-MASTER") -> str:
    """Execute trades or check balances on Binance.

    Actions:
        - 'balance': Show asset balances.
        - 'price': Show current price of a symbol.
        - 'buy': Buy an asset (Market or Limit if price is set).
        - 'sell': Sell an asset.
        - 'portfolio': Show overall portfolio and recent trades.
        - 'history': Show trade history for a symbol.

    Args:
        action: 'balance', 'price', 'buy', 'sell', 'portfolio', or 'history'.
        symbol: e.g., 'BTCUSDT', 'ETHUSDT'.
        amount: Quantity to trade.
        price: Optional limit price.
        user_id: The ID of the user performing the trade.
    """
    from tools.binance_client_tool import BinanceManager
    from tools.portfolio_tracker import PortfolioTracker

    try:
        if action == "portfolio":
            tracker = PortfolioTracker(user_id)
            return tracker.format_summary()

        mgr = BinanceManager(user_id)
        if action == "balance":
            return str(mgr.get_balance())
        if action == "price":
            return str(mgr.get_symbol_price(symbol))
        if action == "buy":
            if not amount: return "Specify amount to buy."
            return str(mgr.execute_trade(symbol, "buy", amount, price))
        if action == "sell":
            if not amount: return "Specify amount to sell."
            return str(mgr.execute_trade(symbol, "sell", amount, price))
        if action == "history":
            return str(mgr.get_history(symbol))

        return f"Unknown binance action: {action}"
    except Exception as e:
        return f"Binance error: {e}"

@tool
def business_analysis_tool(query: str) -> str:
    """Perform deep analysis on business queries, trading strategies, or market trends.

    Args:
        query: The business or trading question to analyze.
    """
    from tools.business_judge import analyze_trade_idea
    try:
        result = analyze_trade_idea(query)
        return str(result)
    except Exception as e:
        return f"Analysis error: {e}"

# ── Export for on-demand loading ──────────────────────────────────────────────
BUSINESS_TOOLS = [binance_tool, business_analysis_tool]
