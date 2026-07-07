#!/usr/bin/env python3
# tools/playground.py — Generate interactive HTML/CSS/JS widgets

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROXY_URL = os.getenv("LLM_PROXY_URL", "http://host.docker.internal:8005/v1")


def generate_widget(description: str) -> str:
    """Generate an interactive HTML widget from a description.
    Returns a __PLAYGROUND__ signal that the frontend renders in a sandboxed iframe."""

    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model="google/gemma-2-9b-it:free",
            base_url=PROXY_URL,
            api_key="proxy-rotate",
            temperature=0.7,
        )

        prompt = f"""You are an expert frontend developer. Generate a single-page interactive HTML widget.

DESCRIPTION: {description}

Output ONLY valid JSON in this exact format — no markdown, no explanation, just raw JSON:
{{"title": "Widget Title", "html": "<div id='app'>...</div>", "css": "body {{ margin:0; ... }}", "js": "document.getElementById('app')..."}}

RULES:
- html: Complete inner HTML for the widget body (no <html>, <head>, <body> tags)
- css: All CSS styles needed (will be injected into <style>)
- js: All JavaScript logic (will be injected into <script>)
- Make it visually polished — use gradients, shadows, smooth animations
- All interactive elements must work (buttons, inputs, canvas, etc.)
- Use modern CSS (flexbox, grid, variables) and vanilla JS only
- Color scheme: dark theme (#0f0f23 background, #e0e0e0 text, #ff6b9d accents)
- No external dependencies — everything inline"""

        resp = llm.invoke([{"role": "user", "content": prompt}])
        raw = resp.content.strip()

        # Try to extract JSON from response
        import re
        json_match = re.search(r'\{[^{}]*"html"[^{}]*"css"[^{}]*"js"[^{}]*\}', raw, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)

        if json_match:
            data = json.loads(json_match.group(0))
            if all(k in data for k in ("html", "css", "js")):
                data.setdefault("title", "Interactive Widget")
                signal = f"__PLAYGROUND__{json.dumps(data, ensure_ascii=False)}"
                print("SPEAK: Widget built successfully.")
                sys.stdout.flush()
                return signal

        return _fallback_widget(description)

    except Exception as e:
        print(f"[Playground Error] {e}", file=sys.stderr)
        return _fallback_widget(description)


def _fallback_widget(description: str) -> str:
    """Generate a basic fallback widget when LLM fails."""
    # Simple interactive demo based on keywords
    desc_lower = description.lower()

    if "logic gate" in desc_lower or "gate" in desc_lower:
        html = '''<div style="padding:20px;font-family:monospace;">
<h2 style="color:#ff6b9d;">Logic Gate Simulator</h2>
<div style="display:flex;gap:12px;margin:16px 0;">
<button onclick="setGate('AND')" class="gate-btn">AND</button>
<button onclick="setGate('OR')" class="gate-btn">OR</button>
<button onclick="setGate('XOR')" class="gate-btn">XOR</button>
<button onclick="setGate('NAND')" class="gate-btn">NAND</button>
<button onclick="setGate('NOR')" class="gate-btn">NOR</button>
</div>
<div style="display:flex;gap:24px;align-items:center;margin:20px 0;">
<div>
<label style="color:#aaa;">Input A:</label><br>
<input type="checkbox" id="a" onchange="eval()" style="width:24px;height:24px;">
</div>
<div>
<label style="color:#aaa;">Input B:</label><br>
<input type="checkbox" id="b" onchange="eval()" style="width:24px;height:24px;">
</div>
<div style="font-size:48px;color:#ff6b9d;" id="out">0</div>
</div>
<div id="truth" style="background:#1a1a2e;padding:12px;border-radius:8px;font-size:13px;"></div>
</div>'''
        css = '''body{margin:0;background:#0f0f23;color:#e0e0e0;padding:16px;}
.gate-btn{background:#1a1a2e;color:#ff6b9d;border:1px solid #ff6b9d;padding:8px 16px;border-radius:6px;cursor:pointer;font-family:monospace;}
.gate-btn:hover{background:#ff6b9d;color:#0f0f23;}
.gate-btn.active{background:#ff6b9d;color:#0f0f23;}'''
        js = '''let gate='AND';
const gates={AND:(a,b)=>a&&b,OR:(a,b)=>a||b,XOR:(a,b)=>a!==b,NAND:(a,b)=>!(a&&b),NOR:(a,b)=>!(a||b)};
function setGate(g){gate=g;document.querySelectorAll('.gate-btn').forEach(b=>b.classList.toggle('active',b.textContent===g));eval();buildTruth();}
function eval(){const a=document.getElementById('a').checked,b=document.getElementById('b').checked;document.getElementById('out').textContent=gates[gate](a,b)?'1':'0';}
function buildTruth(){let h='<b>Truth Table ('+gate+')</b><br>A B | Out<br>';for(let i=0;i<4;i++){const a=!!(i&1),b=!!(i&2);h+=(a?1:0)+' '+(b?1:0)+' | <span style="color:#ff6b9d">'+(gates[gate](a,b)?1:0)+'</span><br>';}document.getElementById('truth').innerHTML=h;}
buildTruth();'''

    elif "timer" in desc_lower or "countdown" in desc_lower:
        html = '''<div style="padding:20px;font-family:monospace;text-align:center;">
<h2 style="color:#ff6b9d;">Countdown Timer</h2>
<div style="margin:20px 0;">
<input type="number" id="mins" value="5" min="0" max="999" style="width:60px;background:#1a1a2e;color:#e0e0e0;border:1px solid #ff6b9d;padding:8px;border-radius:6px;text-align:center;font-size:18px;">
<span style="color:#aaa;"> min</span>
<input type="number" id="secs" value="0" min="0" max="59" style="width:60px;background:#1a1a2e;color:#e0e0e0;border:1px solid #ff6b9d;padding:8px;border-radius:6px;text-align:center;font-size:18px;">
<span style="color:#aaa;"> sec</span>
</div>
<div id="display" style="font-size:64px;color:#ff6b9d;margin:20px 0;">05:00</div>
<div style="display:flex;gap:12px;justify-content:center;">
<button onclick="startTimer()" id="startBtn" style="background:#ff6b9d;color:#0f0f23;border:none;padding:10px 24px;border-radius:6px;cursor:pointer;font-size:16px;">Start</button>
<button onclick="resetTimer()" style="background:#1a1a2e;color:#ff6b9d;border:1px solid #ff6b9d;padding:10px 24px;border-radius:6px;cursor:pointer;font-size:16px;">Reset</button>
</div>
<div id="ring" style="display:none;font-size:48px;margin-top:20px;">🔔 TIME'S UP! 🔔</div>
</div>'''
        css = '''body{margin:0;background:#0f0f23;color:#e0e0e0;font-family:monospace;}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.1)}}
.ring{animation:pulse 0.5s ease-in-out infinite;color:#ff6b9d;}'''
        js = '''let interval,total=0,running=false;
function updateDisplay(){const m=Math.floor(total/60),s=total%60;document.getElementById('display').textContent=String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');}
function startTimer(){if(running)return;total=parseInt(document.getElementById('mins').value)*60+parseInt(document.getElementById('secs').value);if(total<=0)return;running=true;document.getElementById('ring').style.display='none';interval=setInterval(()=>{total--;updateDisplay();if(total<=0){clearInterval(interval);running=false;document.getElementById('ring').style.display='block';}},1000);}
function resetTimer(){clearInterval(interval);running=false;total=0;updateDisplay();document.getElementById('ring').style.display='none';}
updateDisplay();'''

    else:
        # Generic widget
        html = f'''<div style="padding:20px;font-family:monospace;text-align:center;">
<h2 style="color:#ff6b9d;">{description[:50]}</h2>
<p style="color:#aaa;">Widget generated for: {description}</p>
<div style="background:#1a1a2e;padding:20px;border-radius:8px;margin:16px 0;">
<p>Interactive widget coming soon!</p>
</div></div>'''
        css = '''body{margin:0;background:#0f0f23;color:#e0e0e0;font-family:monospace;padding:16px;}'''
        js = '''console.log('Widget loaded');'''

    signal = json.dumps({"title": description[:50], "html": html, "css": css, "js": js}, ensure_ascii=False)
    return f"__PLAYGROUND__{signal}"


if __name__ == "__main__":
    desc = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Hello World"
    print(generate_widget(desc))
