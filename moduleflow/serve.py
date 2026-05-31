#!/usr/bin/env python3
"""Serve ModuleFlow visualization on port 5070."""
import http.server
import os
import sys
from pathlib import Path

PORT = 5070
DIR = Path(__file__).resolve().parent

os.chdir(DIR)
print(f"ModuleFlow running at http://localhost:{PORT}")
print(f"Project root: {DIR.parent}")

handler = http.server.SimpleHTTPRequestHandler
with http.server.HTTPServer(("", PORT), handler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
