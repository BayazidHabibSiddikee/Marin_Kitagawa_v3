#!/usr/bin/env python3
# tools/stock.py — Stock price + graph, runs as its own process
# Usage: python stock.py --ticker AAPL   OR   python stock.py --company "Tesla"

import sys, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import arrow
import yfinance as yf
import matplotlib.pyplot as plt
import matplotlib.dates as mdates



def get_ticker(company_name: str) -> str | None:
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={company_name}"
        res = requests.get(url, headers=headers, timeout=10).json()
        quotes = res.get('quotes', [])
        return quotes[0]['symbol'] if quotes else None
    except Exception as e:
        print(f"Ticker lookup error: {e}")
        return None


def format_table(data, ticker_symbol: str) -> str:
    lines = []
    lines.append(f"   {'Date':<14} \u2502 {'Close':>8}")
    lines.append(f"   {'-'*14}\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    for _, row in data.iterrows():
        d = row['Date'].strftime('%b %d')
        c = f"${row['Close']:.2f}"
        lines.append(f"   {d:<14} \u2502 {c:>8}")
    return "\n".join(lines)


def show_stock(ticker_symbol: str) -> str:
    """Return formatted stock data as a string (no GUI)."""
    try:
        obj = yf.Ticker(ticker_symbol.upper())
        info = obj.info
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        name  = info.get("longName", ticker_symbol)

        if price is None and not info.get("symbol"):
            resolved = get_ticker(ticker_symbol)
            if resolved and resolved.upper() != ticker_symbol.upper():
                return show_stock(resolved)
            return f"Could not retrieve price for {ticker_symbol}."

        if price is None:
            return f"Could not retrieve price for {ticker_symbol}."

        change = info.get("regularMarketChangePercent", 0)
        market_cap = info.get("marketCap")
        volume = info.get("regularMarketVolume")
        high52 = info.get("fiftyTwoWeekHigh")
        low52  = info.get("fiftyTwoWeekLow")

        arrow_sym = "▲" if change >= 0 else "▼"
        lines = [
            f"📈 {name} ({ticker_symbol.upper()})",
            f"   Price: ${price:,.2f}  {arrow_sym} {abs(change):.2f}%",
        ]
        if market_cap:
            mc_b = market_cap / 1e9
            lines.append(f"   Market Cap: ${mc_b:.1f}B")
        if volume:
            lines.append(f"   Volume: {volume:,}")
        if high52 and low52:
            lines.append(f"   52-week: ${low52:,.2f} – ${high52:,.2f}")

        return "\n".join(lines)
    except Exception as e:
        return f"Stock lookup error for {ticker_symbol}: {e}"


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Stock price + 30-day chart")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--ticker', type=str, help="Ticker symbol (e.g. AAPL)")
    group.add_argument('--company', type=str, help="Company name (e.g. Tesla)")
    # Fallback arguments to handle AI hallucinations gracefully
    parser.add_argument('--plot', type=str, help="Fallback plot argument")
    parser.add_argument('--timeframe', type=str, help="Fallback timeframe argument")
    args, unknown = parser.parse_known_args()

    # If AI hallucinates multiple tickers in --plot, try to handle the first one
    if args.plot and not args.ticker and not args.company:
        tickers = [t.strip() for t in args.plot.split(',')]
        args.ticker = tickers[0]
        
    if args.ticker:
        show_stock(args.ticker.upper())
    elif args.company:
        company = args.company
        print(f"\u2192 Looking up ticker for [{company}]")
        ticker = get_ticker(company)
        if ticker:
            show_stock(ticker)
        else:
            print(f"Could not find ticker for {company}")
    else:
        print("No company provided.")
        sys.exit(1)
