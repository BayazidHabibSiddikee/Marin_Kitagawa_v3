import re

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "r") as f:
    html = f.read()

# Add frame to the right wall
html = html.replace(
    "// Left wall — User requested photo\n        makeFrame(0.50, 0.68, [ -W/2+0.03, 1.9, -0.5 ], Math.PI/2, '/static/images/user/wall_photo.jpg', 0x5a1a70);",
    "// Left wall — User requested photo\n        makeFrame(0.50, 0.68, [ -W/2+0.03, 1.9, -0.5 ], Math.PI/2, '/static/images/user/wall_photo.jpg', 0x5a1a70);\n\n        // Right wall — User requested photo\n        makeFrame(0.50, 0.68, [ W/2-0.03, 1.9, -0.5 ], -Math.PI/2, '/static/images/user/wall_photo.jpg', 0x5a1a70);"
)

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "w") as f:
    f.write(html)
