import re

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "r") as f:
    html = f.read()

# Add window.roomMaterials assignment in initRoom
html = html.replace(
    """        // Window / curtain
        const matCurtain = new THREE.MeshLambertMaterial({ color: 0x0a0a0a, side: THREE.DoubleSide });
        const matWindowFr= new THREE.MeshLambertMaterial({ color: 0x222222 });""",
    """        // Window / curtain
        const matCurtain = new THREE.MeshLambertMaterial({ color: 0x0a0a0a, side: THREE.DoubleSide });
        const matWindowFr= new THREE.MeshLambertMaterial({ color: 0x222222 });
        
        window.roomMaterials = { matFloor, matWallBack, matWallSide, matCeil, matDarkWood, matMidWood, matLightWood, matBedFrame, matBedSheet, matPillow, matBlanket, matCouch, matCushion, matPot, matLeaf, matLeafDark, matScreen, matLamp, matMetal, matCurtain, matWindowFr };
        if (typeof syncRoomTheme === 'function') syncRoomTheme();"""
)

# Define syncRoomTheme and add it to applyTheme
html = html.replace(
    "    function applyTheme(name) {",
    """    function syncRoomTheme() {
        if (!window.roomMaterials) return;
        const style = getComputedStyle(document.documentElement);
        const getHex = (v) => parseInt(style.getPropertyValue(v).trim().replace('#', '0x'), 16);
        
        const ink = getHex('--ink');
        const ink2 = getHex('--ink2');
        const ink3 = getHex('--ink3');
        const surface = getHex('--surface');
        const teal = getHex('--teal');
        const tealDim = getHex('--teal-dim');
        
        window.roomMaterials.matWallBack.color.setHex(ink);
        window.roomMaterials.matWallSide.color.setHex(ink2);
        window.roomMaterials.matFloor.color.setHex(surface);
        window.roomMaterials.matCeil.color.setHex(ink3);
        
        window.roomMaterials.matDarkWood.color.setHex(ink);
        window.roomMaterials.matMidWood.color.setHex(ink2);
        window.roomMaterials.matLightWood.color.setHex(ink3);
        
        window.roomMaterials.matCouch.color.setHex(ink2);
        window.roomMaterials.matCushion.color.setHex(surface);
        
        window.roomMaterials.matBedFrame.color.setHex(ink);
        window.roomMaterials.matBedSheet.color.setHex(ink3);
        window.roomMaterials.matPillow.color.setHex(surface);
        window.roomMaterials.matBlanket.color.setHex(ink2);
        
        window.roomMaterials.matLamp.color.setHex(teal);
        window.roomMaterials.matLamp.emissive.setHex(tealDim);
    }

    function applyTheme(name) {"""
)

# Add syncRoomTheme to applyTheme
html = html.replace(
    "        try { localStorage.setItem('marinTheme', name); } catch(e) {}\n        fetch('/api/settings', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ theme: name }) }).catch(e => {});",
    "        try { localStorage.setItem('marinTheme', name); } catch(e) {}\n        fetch('/api/settings', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ theme: name }) }).catch(e => {});\n        if (typeof syncRoomTheme === 'function') syncRoomTheme();"
)

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "w") as f:
    f.write(html)
