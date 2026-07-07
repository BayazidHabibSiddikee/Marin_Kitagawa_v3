import json

import requests

symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
url = f"https://api.binance.com/api/v3/ticker/24hr?symbols={json.dumps(symbols).replace(' ', '')}"
print(url)
res = requests.get(url).json()
for r in res:
    print(r['symbol'], r['lastPrice'], r['priceChangePercent'])
