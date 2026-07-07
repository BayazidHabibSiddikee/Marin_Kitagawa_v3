import re

with open('/home/sword/Documents/marin/marin_fier.py') as f:
    content = f.read()

# Add habit regex
habit_regex = """
    # Habits / Tasks
    if re.search(r'\\b(habit|habits|todo|task)\\b', lower):
        if "status" in lower or "list" in lower:
            return {"intent": "habit_tool", "params": {"action": "list", "args": []}, "confidence": 0.9}
        if "stats" in lower:
            return {"intent": "habit_tool", "params": {"action": "stats", "args": []}, "confidence": 0.9}
        if "today" in lower:
            return {"intent": "habit_tool", "params": {"action": "today", "args": []}, "confidence": 0.9}
        return {"intent": "habit_tool", "params": {"action": "list", "args": []}, "confidence": 0.8}
"""
if "habit_tool" not in content:
    content = content.replace('    # Standard Tools', habit_regex + '\n    # Standard Tools')

# Add LLM classification wrapper
llm_classifier = """
def _llm_classify(text: str) -> dict:
    import json
    import httpx
    try:
        prompt = f'''Classify the message into an intent and user_vibe.
Available intents: [chat, image_gen, learn, code, lab, study, distraction, habit_tool]
Available vibes: [neutral, lovely, flirty, angry, sad, excited]
Message: "{text}"
Respond ONLY with JSON format: {{"intent": "...", "user_vibe": "..."}}'''
        req = {
            "model": "qwen2.5:1.5b",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json"
        }
        resp = httpx.post("http://127.0.0.1:11434/api/chat", json=req, timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            content = data.get("message", {}).get("content", "{}")
            return json.loads(content)
    except Exception:
        pass
    return None

def classify(text: str) -> dict:
    \"\"\"
    Unified classifier for Marin Tools.
    Returns: {intent, params, user_vibe, director_emotion, confidence}
    \"\"\"
    result = _regex_stage(text)

    if result is None:
        llm_res = _llm_classify(text)
        if llm_res and llm_res.get("intent") != "chat":
            result = {"intent": llm_res.get("intent"), "params": {}, "confidence": 0.7}
            if "user_vibe" in llm_res:
                result["user_vibe"] = llm_res["user_vibe"]
        else:
            result = {"intent": "chat", "params": {}, "confidence": 0.8}

    if "user_vibe" not in result:
        result["user_vibe"] = _detect_vibe(text)
    result["director_emotion"] = _detect_director_emotion(text)
    return result
"""
content = re.sub(r'def classify\(text: str\) -> dict:.*?return result', llm_classifier.strip(), content, flags=re.DOTALL)

with open('/home/sword/Documents/marin/marin_fier.py', 'w') as f:
    f.write(content)
