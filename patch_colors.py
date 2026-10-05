import re

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "r") as f:
    html = f.read()

# Replace the materials section
old_mats = """        // ── Materials ────────────────────────────────────────────────────────
        // Floor: warm oak planks
        const matFloor   = new THREE.MeshLambertMaterial({ color: 0x8b6340 });
        // Walls: soft dusty-rose wallpaper with warm cream
        const matWallBack = new THREE.MeshLambertMaterial({ color: 0x3a2e38 });
        const matWallSide = new THREE.MeshLambertMaterial({ color: 0x332833 });
        // Ceiling: off-white
        const matCeil    = new THREE.MeshLambertMaterial({ color: 0x2a2230 });
        // Furniture woods
        const matDarkWood= new THREE.MeshLambertMaterial({ color: 0x3b2510 });
        const matMidWood = new THREE.MeshLambertMaterial({ color: 0x5c3a1e });
        const matLightWood=new THREE.MeshLambertMaterial({ color: 0x8a5c30 });
        // Bed
        const matBedFrame= new THREE.MeshLambertMaterial({ color: 0x2a1a0e });
        const matBedSheet= new THREE.MeshLambertMaterial({ color: 0x4a3f6b });
        const matPillow  = new THREE.MeshLambertMaterial({ color: 0x7a6890 });
        const matBlanket = new THREE.MeshLambertMaterial({ color: 0x6a4a7a });
        // Couch
        const matCouch   = new THREE.MeshLambertMaterial({ color: 0x2c3e50 });
        const matCushion = new THREE.MeshLambertMaterial({ color: 0x3d5166 });
        // Plants
        const matPot     = new THREE.MeshLambertMaterial({ color: 0x7a4f28 });
        const matLeaf    = new THREE.MeshLambertMaterial({ color: 0x2d5a27 });
        const matLeafDark= new THREE.MeshLambertMaterial({ color: 0x1a3d18 });
        // Screen / lamp
        const matScreen  = new THREE.MeshBasicMaterial({ color: 0x1a3a4a });
        const matLamp    = new THREE.MeshBasicMaterial({ color: 0xfff0c0, emissive: 0xfff0c0 });
        const matMetal   = new THREE.MeshLambertMaterial({ color: 0x888888 });
        // Window / curtain
        const matCurtain = new THREE.MeshLambertMaterial({ color: 0x4a2a5a, side: THREE.DoubleSide });
        const matWindowFr= new THREE.MeshLambertMaterial({ color: 0x3a2010 });
        // Wardrobe
        const matWardrobe= new THREE.MeshLambertMaterial({ color: 0x3b2818 });
        const matWardDoor= new THREE.MeshLambertMaterial({ color: 0x4a3322 });
        // Rug
        const matRug     = new THREE.MeshLambertMaterial({ color: 0x6b3a5a });"""

new_mats = """        // ── Materials (CYBERPUNK) ─────────────────────────────────────────────
        // Floor: dark metallic grating
        const matFloor   = new THREE.MeshLambertMaterial({ color: 0x1a1a24 });
        // Walls: very dark grey / purple neon hue
        const matWallBack = new THREE.MeshLambertMaterial({ color: 0x121218 });
        const matWallSide = new THREE.MeshLambertMaterial({ color: 0x0f0f15 });
        // Ceiling: pitch black
        const matCeil    = new THREE.MeshLambertMaterial({ color: 0x050508 });
        // Furniture: dark synthetic metals & matte plastics
        const matDarkWood= new THREE.MeshLambertMaterial({ color: 0x111111 });
        const matMidWood = new THREE.MeshLambertMaterial({ color: 0x22222b });
        const matLightWood=new THREE.MeshLambertMaterial({ color: 0x333340 });
        // Bed
        const matBedFrame= new THREE.MeshLambertMaterial({ color: 0x151515 });
        const matBedSheet= new THREE.MeshLambertMaterial({ color: 0x102030 });
        const matPillow  = new THREE.MeshLambertMaterial({ color: 0x204060 });
        const matBlanket = new THREE.MeshLambertMaterial({ color: 0x081820 });
        // Couch
        const matCouch   = new THREE.MeshLambertMaterial({ color: 0x150020 });
        const matCushion = new THREE.MeshLambertMaterial({ color: 0x250040 });
        // Plants: artificial synthetic neon flora
        const matPot     = new THREE.MeshLambertMaterial({ color: 0x333333 });
        const matLeaf    = new THREE.MeshLambertMaterial({ color: 0x00ff88, emissive: 0x002211 });
        const matLeafDark= new THREE.MeshLambertMaterial({ color: 0x008844 });
        // Screen / lamp
        const matScreen  = new THREE.MeshBasicMaterial({ color: 0x00aaff });
        const matLamp    = new THREE.MeshBasicMaterial({ color: 0x00ffff, emissive: 0x00ffff });
        const matMetal   = new THREE.MeshLambertMaterial({ color: 0x555566 });
        // Window / curtain
        const matCurtain = new THREE.MeshLambertMaterial({ color: 0x0a0a0a, side: THREE.DoubleSide });
        const matWindowFr= new THREE.MeshLambertMaterial({ color: 0x222222 });
        // Wardrobe
        const matWardrobe= new THREE.MeshLambertMaterial({ color: 0x151515 });
        const matWardDoor= new THREE.MeshLambertMaterial({ color: 0x222222 });
        // Rug
        const matRug     = new THREE.MeshLambertMaterial({ color: 0x200030 });"""

html = html.replace(old_mats, new_mats)

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "w") as f:
    f.write(html)
