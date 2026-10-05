with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "r") as f:
    html = f.read()

html = html.replace(
    """<input id="set-location" type="text" placeholder="Tokyo, Japan">
            </div>""",
    """<input id="set-location" type="text" placeholder="Tokyo, Japan">
            </div>
            <div class="set-row">
                <label style="font-size:.65rem;color:var(--text-muted);">Active LLM Model</label>
                <input id="set-active-model" type="text" placeholder="google/gemini-2.5-flash" style="background:var(--ink3);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:4px 8px;width:100%;font-size:.7rem;margin-top:2px;">
            </div>"""
)

html = html.replace(
    "document.getElementById('set-location').value = data.location || '';",
    "document.getElementById('set-location').value = data.location || '';\n            document.getElementById('set-active-model').value = data.active_model || '';"
)

html = html.replace(
    "location: document.getElementById('set-location').value,",
    "location: document.getElementById('set-location').value,\n            active_model: document.getElementById('set-active-model').value,"
)

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "w") as f:
    f.write(html)
