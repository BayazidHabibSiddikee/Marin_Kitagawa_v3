with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "r") as f:
    html = f.read()

import re
html = re.sub(
    r'(<label class="set-label">LOCATION\s*<input id="set-location" type="text">\s*</label>)',
    r'\1\n            <label class="set-label">ACTIVE LLM MODEL\n                <input id="set-active-model" type="text" placeholder="google/gemini-2.5-flash">\n            </label>',
    html
)

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "w") as f:
    f.write(html)
