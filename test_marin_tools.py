#!/usr/bin/env python3
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from langgraph_agent import get_llm
from config import STRATEGY_MODEL

async def main():
    print(f"Testing STRATEGY_MODEL: {STRATEGY_MODEL}")
    llm = get_llm(STRATEGY_MODEL)
    
    # We will simulate a raw message since we just want to see the JSON output
    prompt = """You are generating a synthetic training dataset for an AI agent's tool-calling model.
Output exactly a JSON array of objects with "name" and "arguments" fields.

User Request: "set an alarm for 5 AM"
"""
    try:
        resp = await llm.ainvoke(prompt)
        print("Response Content:\n", resp.content)
    except Exception as e:
        print(f"Error calling model: {e}")

if __name__ == "__main__":
    asyncio.run(main())
