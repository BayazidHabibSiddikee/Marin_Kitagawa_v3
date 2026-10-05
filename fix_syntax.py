import re

new_func = r"""def fix_spacing(text: str) -> str:
    \"\"\"Fix missing spaces between words from small models without modifying control tags/base64.\"\"\"
    if not text:
        return text

    # Protect all __TAG__... control tags from spacing modifications
    protected_tags = []
    def _protect(match):
        protected_tags.append(match.group(0))
        return f"__PROTECTED_TAG_{len(protected_tags)-1}__"

    # Mask __DIRECTOR__...__END__, __YOUTUBE__..., etc.
    masked = re.sub(r'__DIRECTOR__.*?__END__', _protect, text, flags=re.DOTALL)
    masked = re.sub(r'__[A-Z0-9_]+__\S*', _protect, masked)

    # 1. camelCase: wordWord -> word Word
    masked = re.sub(r'([a-z,])([A-Z])', r'\1 \2', masked)
    # 2. Punctuation: word,word -> word, word
    masked = re.sub(r'([,!?;])([a-zA-Z])', r'\1 \2', masked)
    masked = re.sub(r'([.:])([A-Z])', r'\1 \2', masked)
    
    # 3. Restore protected tags
    for i, tag in enumerate(protected_tags):
        masked = masked.replace(f"__PROTECTED_TAG_{i}__", tag)

    return masked"""
new_func = new_func.replace('\\"\\"\\"', '"""')

import ast

def replace_func(filepath):
    with open(filepath, "r") as f:
        content = f.read()
    
    # We will use regex to replace everything from "def fix_spacing" to the next "def " or "# ──"
    # Wait, it's safer to just do a strict regex match.
    pattern = re.compile(r'def fix_spacing\(text: str\) -> str:.*?return masked(?:[\s\S]*?)(?=\n\n(?:@tool|def |# ──))', re.DOTALL)
    
    # Because my previous patch failed and inserted stuff, I will match from 'def fix_spacing' up to 'return masked' and the garbled remainder.
    # Actually, let's just find the exact text bounds manually.
    pass

def manual_replace(filepath):
    with open(filepath, "r") as f:
        lines = f.readlines()
    
    start_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("def fix_spacing(text: str) -> str:"):
            start_idx = i
            break
            
    if start_idx == -1: return
    
    end_idx = -1
    for i in range(start_idx + 1, len(lines)):
        if lines[i].startswith("def ") or lines[i].startswith("@tool") or lines[i].startswith("# ──"):
            end_idx = i
            break
            
    if end_idx == -1: end_idx = len(lines)
    
    new_lines = lines[:start_idx] + [new_func + "\n\n"] + lines[end_idx:]
    with open(filepath, "w") as f:
        f.writelines(new_lines)
    print(f"Fixed {filepath}")

manual_replace("/home/sword/Documents/projects/marin/langgraph_agent.py")
manual_replace("/home/sword/Documents/projects/marin/utils/agent_logic.py")
