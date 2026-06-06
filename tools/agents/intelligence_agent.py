#!/usr/bin/env python3
"""
Intelligence Agent — Web scraping, news aggregation, real-time intelligence.
Marin's eyes and ears on the internet. Gathers, filters, and reports.
"""

import os
import json
import re
from typing import Dict, Any, List
from datetime import datetime

OWNER_USER = "Bayazid"


def action_scrape_url(url: str, max_chars: int = 5000, user: str = OWNER_USER) -> Dict[str, Any]:
    """Scrape a URL and extract text content."""
    import httpx
    try:
        # Use jina reader for clean content
        jina_url = f"https://r.jina.ai/{url}"
        r = httpx.get(jina_url, timeout=15.0, follow_redirects=True)
        if r.status_code == 200:
            text = r.text[:max_chars]
            return {"ok": True, "url": url, "content": text, "length": len(text)}
        return {"ok": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def action_search_news(query: str, max_results: int = 5, user: str = OWNER_USER) -> Dict[str, Any]:
    """Search for recent news on a topic."""
    import httpx
    try:
        # Use DuckDuckGo lite for news search
        url = "https://lite.duckduckgo.com/lite/"
        data = {"q": f"{query} news", "kl": "us-en"}
        r = httpx.post(url, data=data, timeout=10.0)
        # Parse results
        results = []
        links = re.findall(r'class="result-link"[^>]*>(.*?)</a>', r.text, re.DOTALL)
        snippets = re.findall(r'class="result-snippet">(.*?)</td>', r.text, re.DOTALL)

        for i in range(min(len(links), max_results, len(snippets))):
            title = re.sub(r'<[^>]+>', '', links[i]).strip()
            snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            if title and snippet:
                results.append({"title": title, "snippet": snippet})

        return {"ok": True, "query": query, "results": results, "count": len(results)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def action_check_weather(city: str = "Dhaka", user: str = OWNER_USER) -> Dict[str, Any]:
    """Get current weather for a city."""
    import httpx
    try:
        r = httpx.get(f"https://wttr.in/{city}?format=j1", timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            current = data.get("current_condition", [{}])[0]
            return {
                "ok": True, "city": city,
                "temp_c": current.get("temp_C"),
                "temp_f": current.get("temp_F"),
                "humidity": current.get("humidity"),
                "description": current.get("weatherDesc", [{}])[0].get("value", ""),
                "wind_kmph": current.get("windspeedKmph"),
            }
        return {"ok": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def action_get_ip_info(user: str = OWNER_USER) -> Dict[str, Any]:
    """Get current public IP and location info."""
    import httpx
    try:
        r = httpx.get("https://ipinfo.io/json", timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            return {
                "ok": True,
                "ip": data.get("ip"),
                "city": data.get("city"),
                "region": data.get("region"),
                "country": data.get("country"),
                "org": data.get("org"),
                "loc": data.get("loc"),
            }
        return {"ok": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def action_monitor_url(url: str, check_string: str = None, user: str = OWNER_USER) -> Dict[str, Any]:
    """Check if a URL is up and optionally verify content contains expected string."""
    import httpx
    try:
        start = datetime.now()
        r = httpx.get(url, timeout=10.0, follow_redirects=True)
        elapsed = (datetime.now() - start).total_seconds()

        result = {
            "ok": True, "url": url,
            "status_code": r.status_code,
            "response_time_ms": round(elapsed * 1000),
            "content_length": len(r.text),
        }

        if check_string:
            result["contains_string"] = check_string in r.text
            result["string_found"] = check_string in r.text

        return result
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}


def action_extract_links(url: str, user: str = OWNER_USER) -> Dict[str, Any]:
    """Extract all links from a webpage."""
    import httpx
    try:
        jina_url = f"https://r.jina.ai/{url}"
        r = httpx.get(jina_url, timeout=15.0, follow_redirects=True)
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}"}

        links = re.findall(r'\[([^\]]+)\]\((https?://[^\)]+)\)', r.text)
        results = [{"text": text.strip(), "url": link} for text, link in links[:50]]
        return {"ok": True, "url": url, "links": results, "count": len(results)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


ACTIONS = {
    "scrape_url": lambda p, u: action_scrape_url(p.get("url", ""), int(p.get("max_chars", 5000)), u),
    "search_news": lambda p, u: action_search_news(p.get("query", ""), int(p.get("max_results", 5)), u),
    "check_weather": lambda p, u: action_check_weather(p.get("city", "Dhaka"), u),
    "get_ip_info": lambda p, u: action_get_ip_info(u),
    "monitor_url": lambda p, u: action_monitor_url(p.get("url", ""), p.get("check_string"), u),
    "extract_links": lambda p, u: action_extract_links(p.get("url", ""), u),
}


def dispatch(action: str, params: Dict[str, Any], user: str = OWNER_USER) -> Dict[str, Any]:
    fn = ACTIONS.get(action)
    if not fn:
        return {"ok": False, "error": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"}
    try:
        return fn(params, user)
    except Exception as e:
        return {"ok": False, "error": str(e)}
