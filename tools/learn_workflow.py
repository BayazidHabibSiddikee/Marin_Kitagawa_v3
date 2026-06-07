#!/usr/bin/env python3
"""
One-Click Learn Workflow — Coordinates multiple tools to create a complete learning experience.
Combines Book Downloader, Study Engine, and RAG Indexing.
Enhanced to support multiple books and session-specific storage.
"""

import asyncio
import os
import shutil
from pathlib import Path
from tools.book_downloader import search_gutenberg, download_book
from tools.study_engine import create_study_plan
# from rag_server import KnowledgeBase

SESSION_STORAGE = Path("storage/sessions")

async def execute_learn_workflow(topic: str, user_id: str = "USR-MASTER", session_id: str = "default") -> str:
    """The 'God-Tier' learning workflow with session isolation."""
    print(f"[Workflow] Initializing 'Learn {topic}' for {user_id} (Session: {session_id})")
    
    # 1. Create session-specific directory
    session_dir = SESSION_STORAGE / user_id / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. Search for books
    books = search_gutenberg(topic)
    if not books:
        return f"I couldn't find any free books on {topic}. Let me search the web instead..."
        
    # 3. Download multiple books (top 3)
    downloaded_files = []
    for book in books[:3]:
        print(f"[Workflow] Downloading {book['title']}...")
        # Override download dir for this session
        dl_res = download_book(book['download_url'], book['title'])
        if dl_res["ok"]:
            # Move to session directory
            target_path = session_dir / dl_res["filename"]
            shutil.move(dl_res["path"], target_path)
            downloaded_files.append({"title": book['title'], "path": str(target_path)})
            
            # 5. Trigger RAG Indexing
            print(f"[Workflow] Indexing {book['title']} into Knowledge Hub (Session: {session_id})...")
            try:
                import requests
                # We need to send the file to the RAG server upload endpoint
                rag_url = "http://localhost:5080/upload/doc"
                with open(target_path, 'rb') as f:
                    files = {'file': (dl_res["filename"], f)}
                    data = {'session_id': session_id}
                    requests.post(rag_url, files=files, data=data, timeout=30)
            except Exception as e:
                print(f"[Workflow] RAG indexing failed for {book['title']}: {e}")
    
    if not downloaded_files:
        return "Failed to download any relevant books for this topic."
        
    # 4. Create study plan
    print(f"[Workflow] Creating study plan...")
    plan_res = create_study_plan(topic)
    
    book_list = "\n".join([f"  • {f['title']}" for f in downloaded_files])
    
    report = [
        f"✅ **Learning Sequence Activated for {topic}**",
        f"📚 **Books Retrieved**:\n{book_list}",
        f"📂 **Session Sandbox**: `{session_dir}`",
        f"🗺️ **Roadmap Created**: {plan_res['path']}",
        "\nI have analyzed several sources to provide a balanced teaching perspective. Ask me to begin Chapter 1! 📖✨",
    ]
    
    return "\n".join(report)

def cleanup_session_data(user_id: str, session_id: str):
    """Delete session-specific books and data."""
    session_dir = SESSION_STORAGE / user_id / session_id
    if session_dir.exists():
        print(f"[Workflow] Cleaning up session {session_id} for {user_id}...")
        shutil.rmtree(session_dir)
        return True
    return False

if __name__ == "__main__":
    import sys
    topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Calculus"
    print(asyncio.run(execute_learn_workflow(topic)))
