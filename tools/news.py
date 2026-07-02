#!/usr/bin/env python3
# tools/news.py — Fetches real news headlines via RSS for the tool system.
# Falls back to browser-open if RSS fails (original behavior).

import sys
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SOURCES = {
    # International
    "BBC":            "http://feeds.bbci.co.uk/news/rss.xml",
    "AlJazeera":      "https://www.aljazeera.com/xml/rss/all.xml",
    "Reuters":        "https://feeds.reuters.com/reuters/topNews",
    "AP":             "https://rsshub.app/apnews/topics/apf-topnews",
    "DW":             "https://rss.dw.com/xml/rss-en-all",
    "TheGuardian":    "https://www.theguardian.com/international/rss",
    # South Asia
    "DhakaTribune":   "https://www.dhakatribune.com/feed",
    "DailyStarBD":    "https://www.thedailystar.net/frontpage/rss.xml",
    # Financial
    "CNBC":           "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    # Tech
    "TechCrunch":     "https://techcrunch.com/feed/",
    "TheVerge":       "https://www.theverge.com/rss/index.xml",
    # Browser-only fallbacks (no RSS)
    "Bloomberg":      None,
    "FinancialTimes": None,
    "NDTV":           None,
}

# For sources without RSS, fall back to these URLs for __BROWSER__ tag
BROWSER_FALLBACK = {
    "Bloomberg":      "https://www.bloomberg.com/news",
    "FinancialTimes": "https://www.ft.com",
    "NDTV":           "https://www.ndtv.com",
}


def open_news(source: str = "BBC") -> str:
    """Fetch top 5 headlines from an RSS feed. Returns formatted text for tool system."""
    rss_url = SOURCES.get(source)
    
    # If no RSS available, return a browser tag
    if rss_url is None:
        browser_url = BROWSER_FALLBACK.get(source, "https://www.bbc.com/news")
        return f"Opening {source} in the browser~ __BROWSER__{browser_url}"

    try:
        import httpx
        resp = httpx.get(rss_url, timeout=8.0, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; Marin/1.0)"})
        resp.raise_for_status()
        return _parse_rss(resp.text, source)
    except Exception as e:
        # Graceful fallback: return the URL for browser display
        browser_url = BROWSER_FALLBACK.get(source, f"https://www.bbc.com/news")
        return (
            f"Couldn't fetch RSS for {source} ({e.__class__.__name__}). "
            f"Opening in browser instead~ __BROWSER__{browser_url}"
        )


def _parse_rss(xml_text: str, source: str) -> str:
    """Parse RSS XML and return top 5 headlines as a readable string."""
    import re
    
    # Extract <title> tags (skip the first one which is the feed title itself)
    titles = re.findall(r'<title>(?:<!\[CDATA\[)?(.+?)(?:\]\]>)?</title>', xml_text, re.DOTALL)
    # Extract <description> or <summary> for brief snippet
    descs = re.findall(r'<description>(?:<!\[CDATA\[)?(.+?)(?:\]\]>)?</description>', xml_text, re.DOTALL)
    
    # Clean HTML tags from titles/descs
    def clean(s):
        s = re.sub(r'<[^>]+>', '', s)
        s = s.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'")
        return s.strip()
    
    headlines = [clean(t) for t in titles[1:6]]  # skip feed title, take top 5
    
    if not headlines:
        return f"No headlines found from {source}."
    
    lines = [f"📰 Latest from {source}:"]
    for i, h in enumerate(headlines, 1):
        if h:
            lines.append(f"{i}. {h}")
    
    return "\n".join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Fetch news headlines")
    parser.add_argument('--source', type=str, default="BBC",
                        choices=[k for k in SOURCES.keys()],
                        help=f"News source")
    args = parser.parse_args()
    print(open_news(args.source))
