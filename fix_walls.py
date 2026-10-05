import re

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "r") as f:
    html = f.read()

# Fix back wall frame (right of TV) to load frame_couple.png directly, not wall_photo.jpg
html = re.sub(
    r"_wallPhotoRef = makeFrame\(0\.50, 0\.68, \[W\*0\.38, 1\.80, -D/2\+0\.03\], 0, '/static/images/user/wall_photo\.jpg', 0x5a1a70\);",
    r"_wallPhotoRef = makeFrame(0.50, 0.68, [W*0.38, 1.80, -D/2+0.03], 0, '/static/images/frame_couple.png', 0x5a1a70);",
    html
)

# Remove the frame from the actual Right Wall (+W/2) since the user asked to remove "the image you just added"
html = re.sub(
    r"// Right wall — User requested photo\n        makeFrame\(0\.50, 0\.68, \[ W/2-0\.03, 1\.9, -0\.5 \], -Math\.PI/2, '/static/images/user/wall_photo\.jpg', 0x5a1a70\);\n",
    "",
    html
)

# Add Marin's photo (frame_adventure.png) to the Left wall next to the user's photo
# The user's photo is at [ -W/2+0.03, 1.9, -0.5 ]
html = html.replace(
    "// Left wall — User requested photo\n        makeFrame(0.50, 0.68, [ -W/2+0.03, 1.9, -0.5 ], Math.PI/2, '/static/images/user/wall_photo.jpg', 0x5a1a70);",
    "// Left wall — User requested photo\n        makeFrame(0.50, 0.68, [ -W/2+0.03, 1.9, -0.5 ], Math.PI/2, '/static/images/user/wall_photo.jpg', 0x5a1a70);\n        // Left wall — Marin's photo\n        makeFrame(0.68, 0.50, [ -W/2+0.03, 1.9, -1.8 ], Math.PI/2, '/static/images/frame_adventure.png', 0x5a1a70);"
)

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "w") as f:
    f.write(html)
