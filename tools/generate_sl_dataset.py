#!/usr/bin/env python3
import json
import os
import sys
import time
import requests
from pathlib import Path

# Add parent directory to path so we can import langgraph_agent
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from langgraph_agent import ALL_TOOLS
except ImportError as e:
    print(f"Failed to import ALL_TOOLS from langgraph_agent: {e}")
    sys.exit(1)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma4:31b-cloud"
EXAMPLES_PER_TOOL = 200
MULTI_TOOL_PAIRS = 20        # tool pairs to generate multi-call examples for
EXAMPLES_PER_PAIR = 20
OUTPUT_FILE = "marin_tool_dataset.jsonl"

# Concise, schema-free system prompt for every training record. Embedding the
# full JSON schema in each row taught the model to regenerate schemas in its
# output — exactly what strip_tool_schemas() then has to clean up at inference.
SYSTEM_PROMPT = (
    "You are Marin, an AI assistant with access to tools. "
    "When the user's request needs a tool, call it with valid JSON arguments. "
    "Never repeat tool schemas in your reply."
)

def generate_tool_schema(tool):
    """Extracts a clean JSON schema from a Langchain StructuredTool."""
    schema = {
        "name": tool.name,
        "description": tool.description,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
    
    if hasattr(tool, "args_schema") and tool.args_schema:
        raw_schema = tool.args_schema.schema()
        schema["parameters"]["properties"] = raw_schema.get("properties", {})
        schema["parameters"]["required"] = raw_schema.get("required", [])
    
    return schema

def ask_ollama(prompt: str) -> str:
    """Send prompt to local Ollama API."""
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "temperature": 0.8  # High temperature for diverse examples
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        print(f"Ollama API Error: {e}")
        return ""

def main():
    print(f"Discovered {len(ALL_TOOLS)} tools.")
    
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for tool in ALL_TOOLS:
            print(f"\n--- Generating dataset for tool: {tool.name} ---")
            schema = generate_tool_schema(tool)
            schema_json = json.dumps(schema, indent=2)
            
            # Since generating 200 at once might overflow context or cause repetition,
            # we do it in batches of 20
            batches = EXAMPLES_PER_TOOL // 20
            
            for batch in range(batches):
                print(f"Batch {batch+1}/{batches}...")
                prompt = f"""You are generating a synthetic training dataset for an AI agent's tool-calling model.
Below is the JSON schema for a single tool:
```json
{schema_json}
```

Generate 20 completely unique, diverse, and realistic user requests that would trigger this tool.
For each user request, provide the EXACT JSON arguments that should be passed to the tool.

Vary the phrasing heavily! Use slang, formal requests, broken English, and implicit requests.

Output format MUST be exactly a JSON array of objects:
[
  {{"user": "Set an alarm for 5 AM", "arguments": {{"time": "05:00"}}}},
  {{"user": "wake me up at six thirty in the evening", "arguments": {{"time": "18:30"}}}}
]

Output NOTHING ELSE except the raw JSON array.
"""
                response_text = ask_ollama(prompt)
                
                # Cleanup markdown formatting if present
                response_text = response_text.replace("```json", "").replace("```", "").strip()
                
                try:
                    examples = json.loads(response_text)
                    for ex in examples:
                        # Format as ChatML / OpenAI Function Calling standard
                        chatml_record = {
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": ex["user"]},
                                {"role": "assistant", "tool_calls": [{"name": tool.name, "arguments": ex["arguments"]}]}
                            ]
                        }
                        f.write(json.dumps(chatml_record) + "\n")
                    print(f"  + Added {len(examples)} examples.")
                except json.JSONDecodeError:
                    print("  ! Failed to parse JSON from Ollama output. Skipping batch.")
                    print(f"Raw output: {response_text[:100]}...")

        # ── Phase 2: multi-tool examples ─────────────────────────────────────
        # A dataset of single-call rows only never teaches the model to chain
        # tools ("check the weather AND set a timer"), so it can call just one.
        import random
        random.seed(42)  # reproducible pairs across reruns
        print(f"\n=== Phase 2: multi-tool examples ({MULTI_TOOL_PAIRS} pairs) ===")
        for pair_idx in range(MULTI_TOOL_PAIRS):
            tool_a, tool_b = random.sample(ALL_TOOLS, 2)
            print(f"\n--- Pair {pair_idx+1}/{MULTI_TOOL_PAIRS}: {tool_a.name} + {tool_b.name} ---")
            schema_a = json.dumps(generate_tool_schema(tool_a), indent=2)
            schema_b = json.dumps(generate_tool_schema(tool_b), indent=2)

            prompt = f"""You are generating a synthetic training dataset for an AI agent's tool-calling model.
Below are the JSON schemas for TWO tools:
```json
{schema_a}
```
```json
{schema_b}
```

Generate {EXAMPLES_PER_PAIR} unique, realistic user requests that require BOTH tools in one message
(e.g. "check the weather in Dhaka and set a timer for 10 minutes").
For each request, provide the EXACT JSON arguments for each tool call, in the order they should run.

Vary the phrasing heavily! Use slang, formal requests, broken English, and implicit requests.

Output format MUST be exactly a JSON array of objects:
[
  {{"user": "check the weather in Dhaka and set a timer for 10 minutes",
    "calls": [
      {{"name": "{tool_a.name}", "arguments": {{...}}}},
      {{"name": "{tool_b.name}", "arguments": {{...}}}}
    ]}}
]

Output NOTHING ELSE except the raw JSON array.
"""
            response_text = ask_ollama(prompt)
            response_text = response_text.replace("```json", "").replace("```", "").strip()
            try:
                examples = json.loads(response_text)
                valid_names = {tool_a.name, tool_b.name}
                kept = 0
                for ex in examples:
                    calls = ex.get("calls", [])
                    if len(calls) < 2 or any(c.get("name") not in valid_names for c in calls):
                        continue
                    chatml_record = {
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": ex["user"]},
                            {"role": "assistant", "tool_calls": [
                                {"name": c["name"], "arguments": c.get("arguments", {})} for c in calls
                            ]}
                        ]
                    }
                    f.write(json.dumps(chatml_record) + "\n")
                    kept += 1
                print(f"  + Added {kept}/{len(examples)} multi-tool examples.")
            except json.JSONDecodeError:
                print("  ! Failed to parse JSON from Ollama output. Skipping pair.")
                print(f"Raw output: {response_text[:100]}...")

    print(f"\nDone! Dataset saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
