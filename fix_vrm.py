import re

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "r") as f:
    html = f.read()

html = html.replace("loadVRMModel('7931905149146643613.vrm');", "loadVRMModel('marin.vrm');")

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "w") as f:
    f.write(html)
