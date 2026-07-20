#!/usr/bin/env python3
import json
import os
import sys
import random
import requests
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.persona import BASE_CHARACTER_EVIL, VIBE_MODIFIERS

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma4:31b-cloud"
ANIMATIONS_DIR = Path(__file__).resolve().parent.parent / "static" / "animations"
OUTPUT_FILE = "marin_animation_dataset.jsonl"
EXAMPLES_PER_VIBE = 50 

def ask_ollama(prompt: str) -> str:
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "temperature": 0.8 
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=180)
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        print(f"Ollama API Error: {e}")
        return ""

def main():
    if not ANIMATIONS_DIR.exists():
        print(f"Error: {ANIMATIONS_DIR} not found.")
        return

    # Extract all .bvh filenames
    bvh_files = [f.name for f in ANIMATIONS_DIR.glob("*.bvh")]
    print(f"Found {len(bvh_files)} BVH animations.")

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for vibe_name, vibe_prompt in VIBE_MODIFIERS.items():
            print(f"\n--- Generating dataset for VIBE: {vibe_name} ---")
            
            # Select 10 random animations to feed to the LLM as options for this batch
            available_anims = random.sample(bvh_files, min(10, len(bvh_files)))
            
            system_prompt = BASE_CHARACTER_EVIL.replace("{user}", "Limon") + vibe_prompt.replace("{user}", "Limon")
            
            batches = EXAMPLES_PER_VIBE // 5
            for batch in range(batches):
                print(f"Batch {batch+1}/{batches}...")
                
                prompt = f"""You are generating training data for a Text-to-Animation Machine Learning model.
Below is the Persona that the AI MUST strictly follow when speaking:
```
{system_prompt}
```

Below is a list of available 3D animation files (.bvh):
{json.dumps(available_anims, indent=2)}

Task:
Generate 5 diverse, multi-sentence responses that this specific Persona would say to Limon.
For each response, map EXACTLY when (in seconds) the avatar's body language should change by selecting an animation from the list above.

Output EXACTLY a JSON array of objects in this format:
[
  {{
    "text": "Oh, look at you... struggling with basic Python. How adorable. Tell me, do you enjoy being mediocre, Limon? Because I can fix that.",
    "sequence": [
      {{"time_seconds": 0.0, "animation": "amusement.bvh"}},
      {{"time_seconds": 3.5, "animation": "disapproval.bvh"}},
      {{"time_seconds": 7.0, "animation": "evil_laugh.bvh"}}
    ]
  }}
]

RULES:
1. The text MUST perfectly match the Persona's tone, slang, and cruelty/warmth.
2. The animations chosen MUST exist in the provided list.
3. Output NOTHING but the raw JSON array.
"""
                response_text = ask_ollama(prompt)
                
                # Cleanup formatting
                response_text = response_text.replace("```json", "").replace("```", "").strip()
                
                try:
                    examples = json.loads(response_text)
                    for ex in examples:
                        f.write(json.dumps(ex) + "\n")
                    print(f"  + Added {len(examples)} examples.")
                except json.JSONDecodeError:
                    print("  ! Failed to parse JSON from Ollama output. Skipping batch.")
                    print(f"Raw output: {response_text[:100]}...")

    print(f"\nDone! Dataset saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
