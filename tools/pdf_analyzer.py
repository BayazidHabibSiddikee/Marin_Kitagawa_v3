#!/usr/bin/env python3
"""
Smart PDF Analyzer — AI-powered structure detection and summary.
Part of the SwordFish Tools suite.
"""

import os
import fitz # PyMuPDF
from typing import Dict, Any, List

def analyze_pdf(pdf_path: str) -> Dict[str, Any]:
    """Analyze a PDF document for structure and content."""
    if not os.path.exists(pdf_path):
        return {"ok": False, "error": "File not found."}
        
    try:
        doc = fitz.open(pdf_path)
        metadata = doc.metadata
        page_count = doc.page_count
        
        # Extract first 1000 chars for type detection
        first_page = doc[0].get_text()
        text_preview = first_page[:2000]
        
        # Detect type based on keywords
        doc_type = "document"
        if any(x in text_preview.lower() for x in ("textbook", "chapter", "exercise")):
            doc_type = "textbook"
        elif any(x in text_preview.lower() for x in ("abstract", "methods", "references", "cite")):
            doc_type = "research_paper"
        elif any(x in text_preview.lower() for x in ("invoice", "bill", "amount due", "total")):
            doc_type = "invoice/bill"
            
        # Extract TOC if available
        toc = doc.get_toc()
        
        return {
            "ok": True,
            "filename": os.path.basename(pdf_path),
            "type": doc_type,
            "page_count": page_count,
            "metadata": metadata,
            "toc": toc[:10] if toc else [],
            "text_preview": text_preview[:500] + "..."
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(analyze_pdf(sys.argv[1]))
    else:
        print("Usage: python3 pdf_analyzer.py <path_to_pdf>")
