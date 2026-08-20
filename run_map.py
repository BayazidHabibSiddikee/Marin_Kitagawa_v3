#!/usr/bin/env python3
"""Quick CLI to generate/display a map URL via knowledge_hub."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.knowledge_hub import get_map_url

if __name__ == "__main__":
    city = sys.argv[1] if len(sys.argv) > 1 else "Rajshahi"
    destination = sys.argv[2] if len(sys.argv) > 2 else ""
    result = get_map_url(city=city, destination=destination)
    print(result)
