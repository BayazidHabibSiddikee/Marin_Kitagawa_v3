import re

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "r") as f:
    html = f.read()

# Fix the left wall frame (make it portrait)
html = html.replace(
    "makeFrame(0.68, 0.50, [ -W/2+0.03, 1.9, -0.5 ], Math.PI/2, '/static/images/user/wall_photo.jpg', 0x3a2510);",
    "makeFrame(0.50, 0.68, [ -W/2+0.03, 1.9, -0.5 ], Math.PI/2, '/static/images/user/wall_photo.jpg', 0x5a1a70);"
)

# Fix the back wall frame (right of TV) (make it portrait, use wall_photo)
html = re.sub(
    r"_wallPhotoRef = makeFrame\(0\.68, 0\.50, \[W\*0\.38, 1\.80, -D/2\+0\.03\], 0, initial, 0x3a2510\);",
    r"_wallPhotoRef = makeFrame(0.50, 0.68, [W*0.38, 1.80, -D/2+0.03], 0, '/static/images/user/wall_photo.jpg', 0x5a1a70);",
    html
)
html = re.sub(
    r"_wallPhotoRef = makeFrame\(0\.68, 0\.50, \[W\*0\.38, 1\.80, -D/2\+0\.03\], 0, 0x5a3a1a, 0x3a2510\);",
    r"_wallPhotoRef = makeFrame(0.50, 0.68, [W*0.38, 1.80, -D/2+0.03], 0, '/static/images/user/wall_photo.jpg', 0x5a1a70);",
    html
)

# Fix lighting
old_lighting = """        // ── LIGHTING ─────────────────────────────────────────────────────────
        // Cool night ambient
        vrmScene.add(new THREE.AmbientLight(0x1a1530, 0.6));
        // Ceiling pendant warm fill
        const ceilLight = new THREE.PointLight(0xffd580, 1.1, 9);
        ceilLight.position.set(0, H - 0.25, 0);
        vrmScene.add(ceilLight);
        // Soft rim light from left (simulates moonlight through window)
        const rimLight = new THREE.DirectionalLight(0x8899cc, 0.55);
        rimLight.position.set(-5, 3, 2);
        vrmScene.add(rimLight);
        // Warm key light from top-right (main character light)
        const keyLight = new THREE.DirectionalLight(0xffeedd, 0.8);
        keyLight.position.set(3, 4, 3);
        vrmScene.add(keyLight);
        // Bedside lamp glow (already added above with bslLight)
        // TV screen glow (colour matches CSS3D TV)
        const tvGlow = new THREE.PointLight(0x2244aa, 0.4, 3.5);
        tvGlow.position.set(0, 0.82, -D/2+0.5);
        vrmScene.add(tvGlow);
        // Couch area warm bounce
        const couchFill = new THREE.PointLight(0xffaa66, 0.25, 3);
        couchFill.position.set(1.0, 0.8, 2.2);
        vrmScene.add(couchFill);"""

new_lighting = """        // ── LIGHTING (CYBERPUNK) ──────────────────────────────────────────────
        // Deep purple ambient base
        vrmScene.add(new THREE.AmbientLight(0x0f0515, 1.2));
        // Ceiling pendant neon pink fill
        const ceilLight = new THREE.PointLight(0xff00ff, 2.0, 9);
        ceilLight.position.set(0, H - 0.25, 0);
        vrmScene.add(ceilLight);
        // Cyan rim light from left (simulates neon street signs outside)
        const rimLight = new THREE.DirectionalLight(0x00ffff, 1.8);
        rimLight.position.set(-5, 3, 2);
        vrmScene.add(rimLight);
        // Pinkish key light from top-right
        const keyLight = new THREE.DirectionalLight(0xff88ff, 1.0);
        keyLight.position.set(3, 4, 3);
        vrmScene.add(keyLight);
        // TV screen glow (bright cyan)
        const tvGlow = new THREE.PointLight(0x00aaff, 1.2, 4.0);
        tvGlow.position.set(0, 0.82, -D/2+0.5);
        vrmScene.add(tvGlow);
        // Couch area cyan bounce
        const couchFill = new THREE.PointLight(0x00ffff, 1.5, 4.0);
        couchFill.position.set(1.0, 0.8, 2.2);
        vrmScene.add(couchFill);"""

html = html.replace(old_lighting, new_lighting)

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "w") as f:
    f.write(html)
