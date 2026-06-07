# Business Advisor Core

A specialized AI system for stock market analysis, crypto intelligence, and business strategy.

## 🚀 Quick Start

1. **Activate Environment**:
   ```bash
   source activate.sh
   ```

2. **Run Advisor**:
   ```bash
   python3 main.py
   ```
   The advisor runs on port 5069 (default).

## 📊 Core Features

- **Live Market Data**: Real-time integration of stocks (yfinance) and crypto (CoinGecko).
- **Business RAG**: Specialized knowledge retrieval from the `busi_doc/` library (market classics, strategy papers).
- **Sentiment & News**: Live harvesting of financial news and market sentiment.
- **Pure Focus**: Dedicated persona for financial intelligence and strategic advisory.

## 📂 Structure

- `busi_doc/`: Business library (PDFs).
- `storage/`: Persistent market data and history.
- `tools/`: Specialized financial data fetchers and analysis scripts.
- `rag_server.py`: Dedicated indexing engine for business documents.

## 🔧 Capabilities

- `get_stock_info`: Detailed analysis of equities.
- `get_crypto_price`: Real-time crypto price and trend analysis.
- `latest_news`: Financial news aggregator.
- `search_pdfs`: Deep research into the business document library.

---
*Motto: Market intelligence over guesswork. Systems over chaos.*
