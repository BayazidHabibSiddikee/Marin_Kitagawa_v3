#!/usr/bin/env python3
"""
Research Paper Tool — Search and download papers from arXiv.
Part of the SwordFish Tools suite.
"""

import os
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Any

DOWNLOAD_DIR = "static/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def search_arxiv(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search arXiv for research papers."""
    url = f"http://export.arxiv.org/api/query?search_query=all:{query}&max_results={max_results}"
    try:
        response = requests.get(url, timeout=10)
        root = ET.fromstring(response.content)
        
        results = []
        # XML namespace for arXiv
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        for entry in root.findall('atom:entry', ns):
            title = entry.find('atom:title', ns).text.strip()
            summary = entry.find('atom:summary', ns).text.strip()
            # Find PDF link
            dl_url = ""
            for link in entry.findall('atom:link', ns):
                if link.attrib.get('title') == 'pdf':
                    dl_url = link.attrib.get('href')
                    break
                    
            results.append({
                "title": title,
                "summary": summary[:200] + "...",
                "download_url": dl_url,
                "source": "arXiv"
            })
        return results
    except Exception as e:
        print(f"arXiv search error: {e}")
        return []

def download_paper(url: str, title: str) -> Dict[str, Any]:
    """Download a research paper."""
    try:
        if not url.endswith(".pdf") and "arxiv" in url:
            url += ".pdf"
            
        response = requests.get(url, stream=True, timeout=30)
        filename = f"Paper_{title[:30].replace(' ', '_')}.pdf"
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
        print(f"Searching arXiv for '{query}'...")
        res = search_arxiv(query)
        for p in res:
            print(f"- {p['title']} ({p['download_url']})")
    else:
        print("Usage: python3 research_paper.py <query>")
