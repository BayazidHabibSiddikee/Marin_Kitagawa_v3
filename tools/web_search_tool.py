"""
web_search_tool.py — DuckDuckGo web search + lightweight page fetch for Marin.

Logs every search query and result to /home/sword/Documents/projects/marin/logs/browser_activity.log
so the user can watch what Marin searches in real-time.
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path

BROWSER_LOG = Path(os.path.dirname(os.path.abspath(__file__))).parent / "logs" / "browser_activity.log"
os.makedirs(BROWSER_LOG.parent, exist_ok=True)

log = logging.getLogger("browser_activity")
fh = logging.FileHandler(BROWSER_LOG, encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
log.addHandler(fh)
log.setLevel(logging.INFO)


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web using DuckDuckGo. Returns [{title, url, snippet}]."""
    log.info(f"SEARCH: {query}")
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")})
                log.info(f"  RESULT: {r.get('title', '')} — {r.get('href', '')}")
        return results
    except Exception as e:
        log.error(f"  SEARCH_ERROR: {e}")
        return []


def fetch_page(url: str, max_chars: int = 3000) -> str:
    """Fetch a webpage and return its text content."""
    log.info(f"FETCH: {url}")
    try:
        import httpx
        from bs4 import BeautifulSoup
        r = httpx.get(url, timeout=10.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ", strip=True).split())
        log.info(f"  FETCHED: {len(text)} chars from {url}")
        return text[:max_chars]
    except Exception as e:
        log.error(f"  FETCH_ERROR: {url}: {e}")
        return ""


def run(query: str) -> str:
    """Main entry point: search + fetch top result, return formatted summary."""
    results = web_search(query, max_results=3)
    if not results:
        return f"No results found for: {query}"
    lines = [f"🔍 Search: {query}\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. [{r['title']}]({r['url']})\n   {r['snippet'][:200]}")
    # Fetch top result for more detail
    if results[0]["url"]:
        page_text = fetch_page(results[0]["url"])
        if page_text:
            lines.append(f"\n📄 Top result content:\n{page_text[:800]}")
    return "\n".join(lines)
