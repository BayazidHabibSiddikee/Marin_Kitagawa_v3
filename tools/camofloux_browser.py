#!/usr/bin/env python3
"""
Marin Camofloux Browser — Stealth PDF finder and downloader.
Uses Playwright with anti-detection to browse, find PDFs, and download them.
All downloaded PDFs go to /home/marin/Documents/ for auto-RAG ingestion.
SECURITY: SSRF protection — blocks internal/local network access.
"""

import os
import sys
import json
import hashlib
import logging
import ipaddress
import socket
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin, urlparse

LOG_DIR = Path.home() / "logs"
DOWNLOAD_DIR = Path.home() / "Documents"
STATE_FILE = Path.home() / ".config" / "marin" / "browser_state.json"

LOG_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_DIR / "browser.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("camofloux")


# SSRF PROTECTION — block internal/private network access
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("10.0.0.0/8"),       # private Class A
    ipaddress.ip_network("172.16.0.0/12"),    # private Class B
    ipaddress.ip_network("192.168.0.0/16"),   # private Class C
    ipaddress.ip_network("169.254.0.0/16"),   # link-local
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 private
]

_BLOCKED_HOSTS = {
    "localhost", "127.0.0.1", "::1",
    "0.0.0.0", "metadata.google.internal",
    "169.254.169.254",  # AWS/GCP metadata
}


def _is_safe_url(url: str) -> bool:
    """Check if a URL is safe to browse (no SSRF to internal networks)."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        # Check blocked hosts
        if hostname in _BLOCKED_HOSTS:
            log.warning(f"SSRF BLOCKED: {hostname} is in blocked hosts")
            return False

        # Resolve and check IP
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(hostname))
            for net in _BLOCKED_NETWORKS:
                if ip in net:
                    log.warning(f"SSRF BLOCKED: {hostname} resolves to {ip} (internal network)")
                    return False
        except (socket.gaierror, ValueError):
            pass  # Can't resolve — let it through, will fail naturally

        # Block non-HTTP schemes
        if parsed.scheme not in ("http", "https"):
            log.warning(f"SSRF BLOCKED: scheme {parsed.scheme} not allowed")
            return False

        return True
    except Exception:
        return False


def get_stealth_browser():
    """Create a stealth Playwright browser instance."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return None, None

    pw = sync_playwright().start()

    # Stealth browser with anti-detection
    browser = pw.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
        ]
    )

    context = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
        timezone_id="Asia/Dhaka",
        permissions=["geolocation"],
        java_script_enabled=True,
    )

    # Anti-detection scripts
    context.add_init_script("""
        // Override webdriver detection
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        
        // Override chrome detection
        window.chrome = { runtime: {} };
        
        // Override permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
        );
        
        // Override plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        
        // Override languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });
    """)

    return pw, browser, context


def find_pdfs_on_page(page) -> list[str]:
    """Find all PDF links on a page."""
    pdfs = []

    # Find <a> tags with .pdf href
    links = page.query_selector_all('a[href$=".pdf"]')
    for link in links:
        href = link.get_attribute('href')
        if href:
            pdfs.append(href)

    # Find links containing pdf in URL
    all_links = page.query_selector_all('a[href]')
    for link in all_links:
        href = link.get_attribute('href')
        if href and '.pdf' in href.lower() and href not in pdfs:
            pdfs.append(href)

    return list(set(pdfs))


def download_pdf(page, url: str, save_dir: Path) -> str | None:
    """Download a PDF file."""
    try:
        # Make absolute URL
        if not url.startswith('http'):
            current = page.url
            url = urljoin(current, url)

        # Generate filename from URL
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)
        if not filename or not filename.endswith('.pdf'):
            # Generate from hash
            filename = hashlib.md5(url.encode()).hexdigest()[:12] + ".pdf"

        save_path = save_dir / filename

        # Skip if already downloaded
        if save_path.exists():
            log.info(f"  Already exists: {filename}")
            return None

        # Download using page context
        response = page.request.get(url)
        if response.ok:
            save_path.write_bytes(response.body())
            log.info(f"  Downloaded: {filename} ({len(response.body())} bytes)")
            return str(save_path)
        else:
            log.warning(f"  Failed: {url} (status {response.status})")
            return None

    except Exception as e:
        log.error(f"  Download error: {e}")
        return None


def browse_and_collect(start_url: str, max_pages: int = 10) -> dict:
    """Browse a URL, find PDFs, download them."""
    pw, browser, context = get_stealth_browser()
    if not browser:
        return {"error": "Playwright not installed"}

    page = context.new_page()
    downloaded = []
    visited = set()

    try:
        # SSRF CHECK
        if not _is_safe_url(start_url):
            log.warning(f"SSRF BLOCKED: {start_url}")
            return {"ok": False, "error": f"URL blocked by SSRF protection: {start_url}"}

        log.info(f"Browsing: {start_url}")
        page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # Find PDFs on current page
        pdfs = find_pdfs_on_page(page)
        log.info(f"  Found {len(pdfs)} PDFs")

        for pdf_url in pdfs[:20]:  # Limit to 20 PDFs per page
            if _is_safe_url(pdf_url):
                path = download_pdf(page, pdf_url, DOWNLOAD_DIR)
                if path:
                    downloaded.append(path)
            else:
                log.warning(f"SSRF BLOCKED PDF: {pdf_url}")

        # Optionally follow links to find more PDFs
        if max_pages > 1:
            links = page.query_selector_all('a[href]')
            for link in links[:max_pages]:
                try:
                    href = link.get_attribute('href')
                    if href and href not in visited and href.startswith('http'):
                        if not _is_safe_url(href):
                            log.warning(f"SSRF BLOCKED link: {href}")
                            continue
                        visited.add(href)
                        page.goto(href, wait_until="domcontentloaded", timeout=15000)
                        page.wait_for_timeout(1000)
                        more_pdfs = find_pdfs_on_page(page)
                        for pdf_url in more_pdfs[:10]:
                            path = download_pdf(page, pdf_url, DOWNLOAD_DIR)
                            if path:
                                downloaded.append(path)
                except Exception:
                    continue

    except Exception as e:
        log.error(f"Browsing error: {e}")
    finally:
        browser.close()
        pw.stop()

    return {
        "url": start_url,
        "pages_visited": len(visited) + 1,
        "pdfs_downloaded": len(downloaded),
        "files": downloaded,
    }


def search_google_pdfs(query: str, max_results: int = 10) -> dict:
    """Search Google for PDFs and download them."""
    pw, browser, context = get_stealth_browser()
    if not browser:
        return {"error": "Playwright not installed"}

    page = context.new_page()
    downloaded = []

    try:
        search_url = f"https://www.google.com/search?q={query}+filetype:pdf&num={max_results}"
        log.info(f"Google search: {query}")
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # Find PDF links in search results
        pdfs = find_pdfs_on_page(page)
        log.info(f"  Found {len(pdfs)} PDFs in search results")

        for pdf_url in pdfs[:max_results]:
            path = download_pdf(page, pdf_url, DOWNLOAD_DIR)
            if path:
                downloaded.append(path)

    except Exception as e:
        log.error(f"Search error: {e}")
    finally:
        browser.close()
        pw.stop()

    return {
        "query": query,
        "pdfs_downloaded": len(downloaded),
        "files": downloaded,
    }


# ── CLI Interface ──────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Marin Camofloux Browser — PDF Finder")
    sub = parser.add_subparsers(dest="command")

    # Browse command
    browse_cmd = sub.add_parser("browse", help="Browse URL and find PDFs")
    browse_cmd.add_argument("url", help="URL to browse")
    browse_cmd.add_argument("--pages", type=int, default=5, help="Max pages to follow")

    # Search command
    search_cmd = sub.add_parser("search", help="Search Google for PDFs")
    search_cmd.add_argument("query", help="Search query")
    search_cmd.add_argument("--max", type=int, default=10, help="Max results")

    args = parser.parse_args()

    if args.command == "browse":
        result = browse_and_collect(args.url, args.pages)
        print(json.dumps(result, indent=2))
    elif args.command == "search":
        result = search_google_pdfs(args.query, args.max)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
