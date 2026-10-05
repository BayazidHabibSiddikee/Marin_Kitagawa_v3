import re

with open("/home/sword/Documents/projects/marin/main.py", "r") as f:
    py = f.read()

# Add theme to get_settings
py = py.replace(
    '"active_model": database.get_state("ACTIVE_MODEL") or "",',
    '"active_model": database.get_state("ACTIVE_MODEL") or "",\n        "theme": database.get_state("UI_THEME") or "Marin Default",'
)

# Add theme to save_settings
py = py.replace(
    'if data.get("active_model") is not None: database.set_state("ACTIVE_MODEL", data.get("active_model"))',
    'if data.get("active_model") is not None: database.set_state("ACTIVE_MODEL", data.get("active_model"))\n    if data.get("theme") is not None: database.set_state("UI_THEME", data.get("theme"))'
)

with open("/home/sword/Documents/projects/marin/main.py", "w") as f:
    f.write(py)
