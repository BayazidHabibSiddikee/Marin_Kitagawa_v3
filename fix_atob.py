import re

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "r") as f:
    html = f.read()

old_atob = """                            const decoded = atob(dirMatch[1]);"""
new_atob = """                            const decoded = atob(dirMatch[1].replace(/\\s/g, ''));"""
html = html.replace(old_atob, new_atob)

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "w") as f:
    f.write(html)
