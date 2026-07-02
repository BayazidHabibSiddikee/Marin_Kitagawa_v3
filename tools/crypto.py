#!/usr/bin/env python3
# tools/crypto.py — Live crypto price, returns text (no GUI)
# Usage: python crypto.py --coin ethereum

import sys
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Map common short names / symbols to CoinGecko IDs
_COIN_ALIASES = {
    "btc": "bitcoin", "eth": "ethereum", "sol": "solana",
    "bnb": "binancecoin", "ada": "cardano", "xrp": "ripple",
    "doge": "dogecoin", "dot": "polkadot", "avax": "avalanche-2",
    "matic": "matic-network", "link": "chainlink", "ltc": "litecoin",
    "shib": "shiba-inu", "uni": "uniswap", "atom": "cosmos",
}


def run(currency: str = "bitcoin") -> str:
    """Fetch crypto price and return a formatted string (no GUI)."""
    # Normalize alias
    coin = _COIN_ALIASES.get(currency.lower(), currency.lower())

    url = (
        f"https://api.coingecko.com/api/v3/simple/price"
        f"?ids={coin}&vs_currencies=usd"
        f"&include_24hr_change=true&include_market_cap=true&include_24hr_vol=true"
    )
    try:
        data = requests.get(url, headers=HEADERS, timeout=8).json()
        if coin not in data:
            return f"Couldn't find '{currency}' on CoinGecko. Try: bitcoin, ethereum, solana, etc."

        info = data[coin]
        price       = info.get("usd", 0)
        change_24h  = info.get("usd_24h_change", 0)
        market_cap  = info.get("usd_market_cap", 0)
        vol_24h     = info.get("usd_24h_vol", 0)

        arrow_sym = "▲" if change_24h >= 0 else "▼"
        lines = [
            f"💰 {coin.title()} (USD)",
            f"   Price: ${price:,.2f}  {arrow_sym} {abs(change_24h):.2f}% (24h)",
        ]
        if market_cap:
            mc_b = market_cap / 1e9
            lines.append(f"   Market Cap: ${mc_b:.2f}B")
        if vol_24h:
            vol_m = vol_24h / 1e6
            lines.append(f"   24h Volume: ${vol_m:.1f}M")

        return "\n".join(lines)

    except requests.exceptions.Timeout:
        return f"Request timed out fetching {currency} price. Try again in a moment."
    except Exception as e:
        return f"Crypto lookup error for {currency}: {e}"


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Live crypto price")
    parser.add_argument('--coin', type=str, default="bitcoin",
                        help="Coin id: bitcoin, ethereum, solana, etc.")
    args, _ = parser.parse_known_args()
    print(run(args.coin.lower().strip()))
