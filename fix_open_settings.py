import re

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "r") as f:
    html = f.read()

html = html.replace(
    "document.getElementById('set-active-model').value = data.active_model || '';",
    "document.getElementById('set-active-model').value = data.active_model || '';\n            window.serverTheme = data.theme || window.serverTheme;\n            initThemeGrid();"
)

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "w") as f:
    f.write(html)
