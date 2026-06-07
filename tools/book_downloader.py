#!/usr/bin/env python3
"""
Book Downloader — Search and download free books from Project Gutenberg and Open Library.
Part of the SwordFish Tools suite.
"""

import os
import requests
from typing import List, Dict, Any

DOWNLOAD_DIR = "static/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def search_gutenberg(query: str) -> List[Dict[str, Any]]:
    """Search Project Gutenberg via Gutendex API."""
    url = f"https://gutendex.com/books/?search={query}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        results = []
        for book in data.get('results', []):
            # Find PDF or EPUB link
            formats = book.get('formats', {})
            dl_url = formats.get('application/pdf') or formats.get('application/epub+zip') or formats.get('text/plain; charset=utf-8')
            
            results.append({
                "title": book.get('title'),
                "author": ", ".join(a.get('name') for b in [book.get('authors', [])] for a in b),
                "id": book.get('id'),
                "download_url": dl_url,
                "source": "Project Gutenberg"
            })
        return results
    except Exception as e:
        print(f"Gutenberg search error: {e}")
        return []

def search_open_library(query: str) -> List[Dict[str, Any]]:
    """Search Open Library."""
    url = f"https://openlibrary.org/search.json?q={query}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        results = []
        for doc in data.get('docs', [])[:10]:
            # Open Library is trickier for direct downloads, usually redirects to archive.org
            results.append({
                "title": doc.get('title'),
                "author": ", ".join(doc.get('author_name', [])),
                "id": doc.get('key'),
                "download_url": f"https://openlibrary.org{doc.get('key')}",
                "source": "Open Library"
            })
        return results
    except Exception as e:
        print(f"Open Library search error: {e}")
        return []

def download_book(url: str, title: str) -> Dict[str, Any]:
    """Download a book from a URL."""
    try:
        response = requests.get(url, stream=True, timeout=30)
        ext = ".pdf" if "pdf" in url.lower() else ".epub" if "epub" in url.lower() else ".txt"
        filename = f"{title.replace(' ', '_')}{ext}"
        path = os.path.join(DOWNLOAD_DIR, filename)
        
        with open(path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    
        return {"ok": True, "path": path, "filename": filename}
    except Exception as e:
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print("Searching Project Gutenberg...")
        res = search_gutenberg(query)
        for b in res[:3]:
            print(f"- {b['title']} by {b['author']} ({b['download_url']})")
    else:
        print("Usage: python3 book_downloader.py <search query>")
