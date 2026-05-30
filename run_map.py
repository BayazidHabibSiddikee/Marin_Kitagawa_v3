#!/usr/bin/env python3

import sys
sys.path.append('/home/sword/Documents/xMarin')

from marin_fier import tool_create_map

if __name__ == "__main__":
    city = "Rajshahi"
    destination = None  # equivalent to null in the user's request
    result = tool_create_map(city=city, destination=destination)
    print(result)