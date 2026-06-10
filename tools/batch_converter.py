#!/usr/bin/env python3
"""
Batch Converter — Process multiple files at once.
Part of the SwordFish Tools suite.
"""

import os
from typing import List, Dict, Any
from tools.office_tools import pdf_to_xlsx, xlsx_to_pdf, docx_to_pdf, pdf_to_text

def batch_convert_to_pdf(directory: str) -> Dict[str, Any]:
    """Convert all supported files in a directory to PDF."""
    if not os.path.isdir(directory):
        return {"ok": False, "error": "Not a directory."}
        
    results = []
    for filename in os.listdir(directory):
        path = os.path.join(directory, filename)
        if filename.endswith(".docx"):
            out = path.replace(".docx", ".pdf")
            try:
                docx_to_pdf(path, out)
                results.append(out)
            except: pass
        elif filename.endswith(".xlsx"):
            out = path.replace(".xlsx", ".pdf")
            try:
                xlsx_to_pdf(path, out)
                results.append(out)
            except: pass
            
    return {"ok": True, "converted": results}

def batch_extract_text(directory: str) -> Dict[str, Any]:
    """Extract text from all PDFs in a directory."""
    if not os.path.isdir(directory):
        return {"ok": False, "error": "Not a directory."}
        
    results = []
    for filename in os.listdir(directory):
        if filename.endswith(".pdf"):
            path = os.path.join(directory, filename)
            out = path.replace(".pdf", ".txt")
            try:
                pdf_to_text(path, out)
                results.append(out)
            except: pass
            
    return {"ok": True, "extracted": results}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(batch_convert_to_pdf(sys.argv[1]))
    else:
        print("Usage: python3 batch_converter.py <directory>")
