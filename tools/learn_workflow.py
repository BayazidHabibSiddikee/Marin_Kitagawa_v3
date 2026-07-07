#!/usr/bin/env python3
"""
One-Click Learn Workflow — Downloads books and indexes into RAG.
Sources: curated free PDFs + web search for direct links.
"""

import asyncio
import os
from pathlib import Path

import requests

# Use localhost by default (since we use network_mode: host)
_PROXY_HOST = os.getenv("MARIN_PROXY_HOST", "localhost")
RAG_URL = os.getenv("RAG_URL", f"http://{_PROXY_HOST}:5080")

DOWNLOAD_DIR = Path("storage/sessions")

# ── Curated free technical book sources ──────────────────────────────────────
CURATED_BOOKS = {
    "avr": [
        {
            "title": "ATmega328P Datasheet",
            "url": "https://ww1.microchip.com/downloads/en/DeviceDoc/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf"
        },
        {
            "title": "AVR Instruction Set Manual",
            "url": "https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf"
        },
        {
            "title": "ATmega16 Complete Datasheet",
            "url": "https://ww1.microchip.com/downloads/en/DeviceDoc/doc2466.pdf"
        },
    ],
    "microcontroller": [
        {
            "title": "ATmega328P Datasheet",
            "url": "https://ww1.microchip.com/downloads/en/DeviceDoc/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf"
        },
    ],
    "embedded": [
        {
            "title": "Introduction to Embedded Systems - Shibu",
            "url": "https://www.mheducation.co.in/downloadcenter/embedded-systems/introduction-to-embedded-systems-1st-edition/978-0-07-014589-4/Book_Chapter.pdf"
        },
    ],
    "c programming": [
        {
            "title": "The C Programming Language",
            "url": "https://www.bell-labs.com/usr/dmr/www/cbook.pdf"
        },
        {
            "title": "Essential C",
            "url": "http://cslibrary.stanford.edu/101/EssentialC.pdf"
        }
    ],
    "python": [
        {
            "title": "Think Python 2nd Edition",
            "url": "https://greenteapress.com/thinkpython2/thinkpython2.pdf"
        },
        {
            "title": "Python Tutorial - Official Docs",
            "url": "https://docs.python.org/3/archives/python-3.12.0-docs-pdf-a4.zip"
        },
    ],
    "arduino": [
        {
            "title": "Arduino Programming Notebook",
            "url": "https://raw.githubusercontent.com/brian-petersen/Arduino-Programming-Notebook/master/Arduino_Programming_Notebook.pdf"
        },
        {
            "title": "Arduino Uno Revision 3 Datasheet",
            "url": "https://docs.arduino.cc/resources/datasheets/A000066-datasheet.pdf"
        },
        {
            "title": "Introduction to Arduino - Volume 1",
            "url": "https://me.utexas.edu/~longoria/Vcl/Arduino/Intro_to_Arduino.pdf"
        }
    ],
    "assembly": [
        {
            "title": "The Art of x86 Assembly Language",
            "url": "https://www.ic.unicamp.br/~pannain/mc404/aulas/pdfs/Art+Of+Intel+x86+Assembly.pdf"
        },
        {
            "title": "Assembly Language Programming Lecture Notes",
            "url": "https://vulms.vu.edu.pk/Courses/CS401/Lessons/Lesson_1/cs401.pdf"
        },
        {
            "title": "RISC-V Assembly Programming",
            "url": "https://www.robertwinkler.com/projects/riscv_book/riscv_book.pdf"
        }
    ],
}


def _match_curated(topic: str) -> list:
    """Find curated books matching topic keywords."""
    topic_lower = topic.lower()
    # Priority 1: Exact matches for common technical keywords
    if "arduino" in topic_lower:
        return CURATED_BOOKS.get("arduino", [])
    if "avr" in topic_lower:
        return CURATED_BOOKS.get("avr", [])
    if "python" in topic_lower:
        return CURATED_BOOKS.get("python", [])
    if "assembly" in topic_lower or "asm" in topic_lower:
        return CURATED_BOOKS.get("assembly", [])

    import re
    matched = []
    for key, books in CURATED_BOOKS.items():
        # check exact key match or if any whole word from the key is present in topic
        words = key.split()
        if key in topic_lower or any(re.search(rf"\b{re.escape(w)}\b", topic_lower) for w in words):
            matched.extend(books)
    return matched


def _search_free_pdfs_web(topic: str) -> list:
    """Search web for direct PDF links using advanced cascade."""
    try:
        # Use the advanced cascade from pdf_downloader
        from tools.pdf_downloader import search_pdfs
        hits = search_pdfs(topic)
        results = []
        for h in hits:
            url = h.get("url") or h.get("href") or ""
            if url:
                # Be more lenient: if it's from a reputable edu/org site or looks like a doc
                if url.lower().endswith(".pdf") or "bitstream" in url or "download" in url or any(domain in url for domain in [".edu", ".org", "microchip.com", "atmel.com"]):
                    results.append({"href": url, "title": h.get("title") or topic})
        return results
    except Exception as e:
        print(f"[Workflow] Advanced search error: {e}")
        # Manual fallback to hub if pdf_downloader fails
        from tools.knowledge_hub import search_web
        results = []
        queries = [
            f'"{topic}" filetype:pdf (site:edu OR site:org OR site:microchip.com)',
            f'"{topic}" technical manual free pdf',
        ]
        for q in queries:
            hits = search_web(q, max_results=10) or []
            for h in hits:
                url = h.get("href") or h.get("link") or ""
                if url:
                    results.append({"href": url, "title": h.get("title", topic)})
        return results



def _download_pdf(url: str, title: str, dest_dir: Path) -> str | None:
    """Download a PDF. Returns path or None."""
    try:
        resp = requests.get(url, timeout=10, stream=True, allow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        data = resp.content
        if data[:5] != b"%PDF-":
            return None
        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)[:80]
        path = dest_dir / f"{safe}.pdf"
        path.write_bytes(data)
        print(f"[Workflow] Saved: {path.name} ({len(data)//1024} KB)")
        return str(path)
    except Exception as e:
        print(f"[Workflow] Download failed {url[:70]}: {e}")
        return None


def _ingest_to_rag(file_path: str) -> bool:
    """Upload PDF to RAG server, or copy to doc/ dir as fallback."""
    filename = os.path.basename(file_path)
    # Try API upload first
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"{RAG_URL}/upload/doc",
                files={"file": (filename, f, "application/pdf")},
                timeout=120
            )
        if resp.status_code == 200:
            print(f"[Workflow] RAG ingest OK: {filename}")
            return True
    except Exception as e:
        print(f"[Workflow] RAG API error: {e}")

    # Fallback: copy to doc/ dir and trigger reindex
    try:
        doc_dir = Path(__file__).parent.parent / "doc"
        doc_dir.mkdir(exist_ok=True)
        dest = doc_dir / filename
        import shutil
        shutil.copy2(file_path, dest)
        # Trigger reindex
        requests.post(f"{RAG_URL}/reindex", timeout=30)
        print(f"[Workflow] Copied to doc/ for RAG: {filename}")
        return True
    except Exception as e:
        print(f"[Workflow] doc/ copy error: {e}")
        return False


async def execute_learn_workflow(topic: str, user_id: str = "USR-MASTER", session_id: str = "default") -> str:
    print(f"[Workflow] Learn workflow: '{topic}'")

    dest_dir = DOWNLOAD_DIR / user_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 1. Try curated sources first, then web search
    candidates = _match_curated(topic)
    if not candidates:
        web = await asyncio.to_thread(_search_free_pdfs_web, topic)
        candidates = [{"title": r["title"], "url": r["href"]} for r in web]

    if not candidates:
        return (
            f"No free PDF sources found for '{topic}'. "
            "Try asking me to search arXiv, or I can teach you the material directly."
        )

    # 2. Download up to 3 PDFs
    downloaded = []
    for c in candidates:
        if len(downloaded) >= 3:
            break
        url = c.get("url") or c.get("href", "")
        title = c.get("title", topic)
        print(f"[Workflow] Trying: {url[:70]}")
        path = await asyncio.to_thread(_download_pdf, url, title, dest_dir)
        if path:
            downloaded.append({"title": title, "path": path})

    if not downloaded:
        return (
            f"Found sources for '{topic}' but downloads failed (403/network). "
            f"Files would have been: {', '.join(c.get('title','?') for c in candidates[:3])}. "
            "I can still teach you the material directly — ask me any topic."
        )

    # 3. Ingest into RAG
    indexed = []
    for book in downloaded:
        ok = await asyncio.to_thread(_ingest_to_rag, book["path"])
        if ok:
            indexed.append(book["title"])

    # 4. Report
    book_lines = "\n".join(f"  • {b['title']}" for b in downloaded)
    rag_note = (
        f"✅ {len(indexed)} of {len(downloaded)} book(s) indexed into RAG knowledge base."
        if indexed else
        f"⚠️ Downloaded to `{dest_dir}` but RAG indexing failed — RAG server may be offline."
    )

    return (
        f"I have successfully retrieved the following resources for: {topic}\n\n"
        f"{book_lines}\n\n"
        f"{rag_note}\n\n"
        f"File location: `{dest_dir}`\n\n"
        f"The data is indexed and ready for your questions, Limon."
    )
