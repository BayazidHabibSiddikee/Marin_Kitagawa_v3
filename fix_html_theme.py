import re

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "r") as f:
    html = f.read()

# Add a fetch call to applyTheme
html = html.replace(
    "try { localStorage.setItem('marinTheme', name); } catch(e) {}",
    "try { localStorage.setItem('marinTheme', name); } catch(e) {}\n        fetch('/api/settings', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ theme: name }) }).catch(e => {});"
)

# Update initThemeGrid to read from window.serverTheme
html = html.replace(
    "let saved = 'Marin Default'; try { saved = localStorage.getItem('marinTheme') || 'Marin Default'; } catch(e) {}",
    "let saved = window.serverTheme || 'Marin Default'; try { saved = localStorage.getItem('marinTheme') || saved; } catch(e) {}"
)

# Update restoreSavedTheme to read from window.serverTheme
html = html.replace(
    "let saved = null; try { saved = localStorage.getItem('marinTheme'); } catch(e) {}",
    "let saved = window.serverTheme || null; try { saved = localStorage.getItem('marinTheme') || saved; } catch(e) {}"
)

# Add window.serverTheme definition at the top of the script
html = html.replace(
    "const BASE_URL = window.location.origin;",
    "const BASE_URL = window.location.origin;\n    window.serverTheme = `{{ user.get_state('UI_THEME') or '' }}`;"
)

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "w") as f:
    f.write(html)
