import re

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "r") as f:
    html = f.read()

# Fix initThemeGrid
html = re.sub(
    r"const saved = localStorage\.getItem\('marinTheme'\) \|\| 'Marin Default';",
    r"let saved = 'Marin Default'; try { saved = localStorage.getItem('marinTheme') || 'Marin Default'; } catch(e) {}",
    html
)

# Fix applyTheme
html = re.sub(
    r"localStorage\.setItem\('marinTheme', name\);",
    r"try { localStorage.setItem('marinTheme', name); } catch(e) {}",
    html
)

# Fix restoreSavedTheme
html = re.sub(
    r"const saved = localStorage\.getItem\('marinTheme'\);",
    r"let saved = null; try { saved = localStorage.getItem('marinTheme'); } catch(e) {}",
    html
)

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "w") as f:
    f.write(html)
