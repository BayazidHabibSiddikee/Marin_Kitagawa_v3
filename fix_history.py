import re

with open("/home/sword/Documents/projects/marin/utils/agent_logic.py", "r") as f:
    py = f.read()

# Replace the history comprehension with a cleaned version
old_history = """    fast_msgs = [
        {"role": "system", "content": system + context_instruction},
        *[{"role": m["role"], "content": m["content"]} for m in history],
        {"role": "user", "content": prompt}
    ]"""

new_history = """    # Clean history of control tags so LLM doesn't learn to generate them
    clean_history = []
    for m in history:
        clean_text = m["content"]
        clean_text, _ = extract_control_tags(clean_text)
        clean_text = re.sub(r'__VIBE__\\S+', '', clean_text)
        clean_history.append({"role": m["role"], "content": clean_text.strip()})

    fast_msgs = [
        {"role": "system", "content": system + context_instruction},
        *[{"role": m["role"], "content": m["content"]} for m in clean_history if m["content"]],
        {"role": "user", "content": prompt}
    ]"""

py = py.replace(old_history, new_history)

with open("/home/sword/Documents/projects/marin/utils/agent_logic.py", "w") as f:
    f.write(py)
