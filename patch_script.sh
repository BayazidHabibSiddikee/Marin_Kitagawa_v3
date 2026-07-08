#!/bin/bash
patch -p1 << 'PATCH_EOF'
--- a/database.py
+++ b/database.py
@@ -19,6 +19,17 @@
 T = TypeVar("T")
 
+class ManagedConnection:
+    """A wrapper to prevent sqlite3 connection from closing on __exit__."""
+    def __init__(self, conn):
+        self.conn = conn
+    def __enter__(self):
+        return self.conn
+    def __exit__(self, exc_type, exc_val, exc_tb):
+        pass
+    def __getattr__(self, name):
+        return getattr(self.conn, name)
+
 def get_db_connection():
     """Return a thread-local SQLite connection (reused per thread)."""
     os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
@@ -29,7 +40,7 @@
         conn.execute("PRAGMA journal_mode=WAL")
         conn.execute("PRAGMA busy_timeout=5000")
         _local.conn = conn
-    return conn
+    return ManagedConnection(conn)
 
 def _db_op(fn: Callable[..., T], default: T = None) -> T:
--- a/templates/marin_chat.html
+++ b/templates/marin_chat.html
@@ -37,6 +37,11 @@
     <script src="https://unpkg.com/@pixiv/three-vrm@2.0.0/lib/three-vrm.js"></script>
     <style>
+        :root {
+            --msuccess: #5db882;
+            --gold-dim: rgba(201, 150, 90, 0.2);
+        }
+        .provider-body.collapsed { display: none; }
         #vrm-container {
             width: 35%;
             min-width: 250px;
@@ -1757,12 +1762,23 @@
             <button onclick="this.parentElement.remove()" style="background:none;border:1px solid var(--border);color:var(--danger);width:24px;height:24px;border-radius:var(--radius-sm);cursor:pointer;font-size:.6rem;flex-shrink:0;">×</button>`;
         list.appendChild(row);
     }
 
+    function escapeHtml(unsafe) {
+        if (!unsafe) return '';
+        return unsafe
+             .toString()
+             .replace(/&/g, "&amp;")
+             .replace(/</g, "&lt;")
+             .replace(/>/g, "&gt;")
+             .replace(/"/g, "&quot;")
+             .replace(/'/g, "&#039;");
+    }
+
     // ── Collect provider state from DOM ────────────────────────
     function collectProvidersFromDOM() {
         return Array.from(document.querySelectorAll('.provider-card')).map((card, idx) => {
             const keys = Array.from(card.querySelectorAll('.prov-key-input')).map(i => i.value.trim()).filter(Boolean);
-            const isOR = (card.querySelector('.prov-base-url')?.value || '').includes('openrouter');
+            const baseUrl = card.querySelector('.prov-base-url')?.value?.toLowerCase() || '';
+            const isOR = baseUrl.includes('openrouter') || baseUrl.includes('openai') || baseUrl.includes('anthropic') || baseUrl.includes('groq') || baseUrl.includes('deepseek') || baseUrl.includes('xai') || baseUrl.includes('google');
             let models;
             if (isOR) {
@@ -1813,6 +1829,8 @@
         }
     }
 
+    let _pendingAvatar = null;
+    
     // ── Open / Close / Save ────────────────────────────────────
     async function openSettings() {
         document.getElementById('settings-modal').classList.add('open');
--- a/langgraph_agent.py
+++ b/langgraph_agent.py
@@ -469,8 +469,8 @@
     business_analysis_tool, binance_tool
 ]
 
-# Default: use CORE_TOOLS only (follow Custom Instruction §3)
-ALL_TOOLS = CORE_TOOLS
+# Use CORE_TOOLS and BUSINESS_TOOLS
+ALL_TOOLS = CORE_TOOLS + BUSINESS_TOOLS
 tools_by_name = {t.name: t for t in ALL_TOOLS}
 
 # ── Agent State ──────────────────────────────────────────────────────────────
--- a/utils/tool_registry.py
+++ b/utils/tool_registry.py
@@ -57,11 +57,11 @@
 
     for domain, data in TOOL_DOMAINS.items():
         score = sum(1 for kw in data["keywords"] if re.search(r'\b' + kw + r'\b', lower_query))
-        if score > best_score:
+        if score >= threshold and score >= best_score:
             best_score = score
             best_domain = domain
 
-    if best_score > 0 and best_domain:
+    if best_score >= threshold and best_domain:
         print(f"[SemanticRouter] Matched Domain: {best_domain} (Score: {best_score})")
         return TOOL_DOMAINS[best_domain]["tools"]
--- a/marin_fier.py
+++ b/marin_fier.py
@@ -258,7 +258,7 @@
     import httpx
     try:
         prompt = f'''Classify the message into an intent and user_vibe.
-Available intents: [chat, image_gen, learn, code, lab, study, distraction, habit_tool]
+Available intents: [Finance, Media, System, Research, Productivity, Games, Maths, Study, chat, image_gen, code, habit_tool]
 Available vibes: [neutral, lovely, flirty, angry, sad, excited]
 Message: "{text}"
 Respond ONLY with JSON format: {{"intent": "...", "user_vibe": "..."}}'''
--- a/templates/index.html
+++ b/templates/index.html
@@ -6,27 +6,26 @@
     <meta name="viewport" content="width=device-width, initial-scale=1.0">
     <title> HS-02 — Command Center</title>
     <link rel="preconnect" href="https://fonts.googleapis.com">
-    <link
-        href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600;700&family=DM+Sans:wght@400;500;600;700&family=Rajdhani:wght@400;500;600;700&family=Share+Tech+Mono&display=swap"
-        rel="stylesheet">
+    <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400&family=Rajdhani:wght@400;500;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">
+    <link rel="stylesheet" href="/static/theme.css">
     <!-- KaTeX for LaTeX formula rendering -->
     <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9/katex.min.css">
     <script src="https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9/katex.min.js"></script>
     <script src="https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9/contrib/auto-render.min.js"></script>
     <style>
         :root {
-            --bg: #13100e;
-            --bg2: #1c1814;
-            --panel: #221e19;
-            --border: #3a342c;
-            --purple: #4db8a4; /* Teal mapping */
-            --violet: #2d8a78;
-            --text: #e8ddd0;
-            --dim: #8a7d72;
-            --muted: #4a4038;
-            --danger: #e07b6a; /* Coral mapping */
-            --gold: #c9965a;
-            --success: #5db882;
+            --bg: var(--ink);
+            --bg2: var(--ink2);
+            --panel: var(--ink3);
+            --border: var(--border);
+            --purple: var(--teal);
+            --violet: var(--teal-dim);
+            --text: var(--text);
+            --dim: var(--text-dim);
+            --muted: var(--text-muted);
+            --danger: var(--coral);
+            --gold: var(--gold);
+            --success: var(--success);
         }
 
         * {
@@ -532,13 +531,15 @@
     <div class="orb orb-2"></div>
 
     <!-- NAV -->
-    <nav>
-        <div class="nav-brand">
+    <nav class="topbar">
+        <a href="/" class="nav-brand">
             MARIN
             <span class="hs">HS-02</span>
-        </div>
+        </a>
         <div class="nav-links">
-            <a href="/">HOME</a>
+            <a href="/" class="active">HOME</a>
+            <a href="/profile">PROFILE</a>
+            <a href="/sentinel">SENTINEL</a>
             <a href="/chat" class="cta">⚔ ENTER COMMAND CENTER</a>
         </div>
     </nav>
--- a/templates/profile.html
+++ b/templates/profile.html
@@ -6,24 +6,25 @@
     <meta name="viewport" content="width=device-width, initial-scale=1.0">
     <title> HS-02 — Profile</title>
     <link rel="preconnect" href="https://fonts.googleapis.com">
-    <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&family=JetBrains+Mono:wght@300;400&display=swap" rel="stylesheet">
+    <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;700&display=swap" rel="stylesheet">
+    <link rel="stylesheet" href="/static/theme.css">
     <style>
         :root {
-            --bg: #13100e;
-            --bg2: #1c1814;
-            --panel: #221e19;
-            --border: #3a342c;
-            --purple: #4db8a4;
-            --violet: #2d8a78;
-            --text: #e8ddd0;
-            --dim: #8a7d72;
-            --muted: #4a4038;
-            --danger: #e07b6a;
-            --gold: #c9965a;
-            --success: #10b981;
+            --bg: var(--ink);
+            --bg2: var(--ink2);
+            --panel: var(--ink3);
+            --border: var(--border);
+            --purple: var(--teal);
+            --violet: var(--teal-dim);
+            --text: var(--text);
+            --dim: var(--text-dim);
+            --muted: var(--text-muted);
+            --danger: var(--coral);
+            --gold: var(--gold);
+            --success: var(--success);
             
-            --teal: #4db8a4;
-            --teal-dim: #2d8a78;
+            --teal: var(--teal);
+            --teal-dim: var(--teal-dim);
         }
 
         * {
@@ -743,12 +744,16 @@
 
 <body>
 
-    <nav>
-        <div class="nav-brand">MARIN <span class="hs">HS-02</span></div>
+    <nav class="topbar">
+        <a href="/" class="nav-brand">
+            MARIN
+            <span class="hs">HS-02</span>
+        </a>
         <div class="nav-links">
             <a href="/">HOME</a>
-            <a href="/chat">CHAT</a>
             <a href="/profile" class="active">PROFILE</a>
+            <a href="/sentinel">SENTINEL</a>
+            <a href="/chat" class="cta">⚔ ENTER COMMAND CENTER</a>
         </div>
     </nav>
 
--- a/templates/command_center.html
+++ b/templates/command_center.html
@@ -4,18 +4,20 @@
     <meta charset="UTF-8">
     <meta name="viewport" content="width=device-width, initial-scale=1.0">
     <title>Marin OS — Command Center</title>
+    <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;700&display=swap" rel="stylesheet">
+    <link rel="stylesheet" href="/static/theme.css">
     <style>
         * { margin: 0; padding: 0; box-sizing: border-box; }
         body {
             font-family: 'JetBrains Mono', 'Fira Code', monospace;
-            background: #0a0a0f;
-            color: #e0e0e0;
+            background: var(--ink);
+            color: var(--text);
             min-height: 100vh;
         }
         .header {
-            background: linear-gradient(135deg, #1a1a2e 0%, #0f0f1a 100%);
+            background: var(--ink2);
             padding: 20px 30px;
-            border-bottom: 2px solid #e94560;
+            border-bottom: 1px solid var(--border);
             display: flex;
             justify-content: space-between;
             align-items: center;
@@ -212,11 +214,23 @@
     </style>
 </head>
 <body>
+    <nav class="topbar">
+        <a href="/" class="nav-brand">
+            MARIN
+            <span class="hs">HS-02</span>
+        </a>
+        <div class="nav-links">
+            <a href="/">HOME</a>
+            <a href="/profile">PROFILE</a>
+            <a href="/sentinel">SENTINEL</a>
+            <a href="/chat" class="cta">⚔ ENTER COMMAND CENTER</a>
+        </div>
+    </nav>
     <div class="header">
         <div>
-            <h1>MARIN OS</h1>
+            <h1 style="color:var(--teal)">MARIN OS</h1>
             <div class="subtitle">Command Center v3.0</div>
-            <a href="/sentinel" style="color:#e94560;font-size:11px;text-decoration:none;margin-top:8px;display:inline-block;border:1px solid #e94560;padding:2px 6px;border-radius:4px;">[ SENTINEL PROXY ]</a>
+            <a href="/sentinel" style="color:var(--coral);font-size:11px;text-decoration:none;margin-top:8px;display:inline-block;border:1px solid var(--coral);padding:2px 6px;border-radius:4px;">[ SENTINEL PROXY ]</a>
         </div>
         <span id="status-badge" class="status-badge status-offline">CHECKING...</span>
     </div>
PATCH_EOF
bash patch_script.sh
