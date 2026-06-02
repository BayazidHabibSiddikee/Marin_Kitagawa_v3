import os
import re
import sys
import requests

# ── Configuration ──────────────────────────────────────────────────────────────
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "unique", "download")
REQUEST_TIMEOUT = 30

def validate_pdf(data: bytes) -> bool:
    """Check if downloaded data is a valid PDF (magic bytes)."""
    if len(data) < 5:
        return False
    return data[:5] == b"%PDF-"

def _sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    name = name.strip('._')
    return name[:200] if name else "untitled"

def download_pdf(url: str, book_name: str, output_dir: str = None) -> str:
    """
    Download a PDF from url, save as book_name.pdf.
    Returns the saved file path, or empty string on failure.
    """
    if output_dir is None:
        output_dir = DEFAULT_DOWNLOAD_DIR
    os.makedirs(output_dir, exist_ok=True)

    filename = _sanitize_filename(book_name) + ".pdf"
    filepath = os.path.join(output_dir, filename)

    try:
        print(f"  [download] {url[:80]}...")
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, stream=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()

        data = resp.content

        # Validate PDF
        if not validate_pdf(data):
            if b"<html" in data[:500].lower():
                print(f"  [reject] Got HTML instead of PDF from {url[:60]}")
                return ""
            return ""

        with open(filepath, "wb") as f:
            f.write(data)

        print(f"  [saved] {filepath}")
        return filepath

    except Exception as e:
        print(f"  [error] Download failed: {e}")
        return ""

def marin_search_and_download(query: str, download_dir: str = None) -> str:
    """Marin's internal logic: search via existing knowledge_hub and download via this tool."""
    from tools.knowledge_hub import search_web
    
    # search_web handles the heavy lifting
    pdf_query = f"{query} filetype:pdf"
    results = search_web(pdf_query, max_results=10)
    
    if not results:
        return f"I couldn't find any direct links for '{query}'."

    for i, r in enumerate(results[:5], 1):
        href = r.get("href") or r.get("link") or ""
        if not href: continue
        
        path = download_pdf(href, query, download_dir)
        if path:
            return os.path.abspath(path)
            
    return ""
