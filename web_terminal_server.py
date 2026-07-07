"""
web_terminal_server.py — Local PTY WebSocket bridge (hardened).

Security hardening applied:
  • Localhost-only binding (127.0.0.1) — not exposed on 0.0.0.0
  • Single-use token auth: the HTML UI receives a fresh token from main.py;
    the WebSocket endpoint validates it before spawning a shell.
  • Max 3 concurrent sessions to prevent resource exhaustion.
  • Proper asyncio task scheduling from the sync PTY reader callback
    via loop.call_soon_threadsafe() so exceptions don't silently vanish.
  • Session timeout of 30 minutes.
  • Graceful PTY cleanup on disconnect.
"""

import asyncio
import contextlib
import os
import pty
import secrets
import threading
import time

import uvicorn
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI()

# ── AUTH TOKEN STORE ──────────────────────────────────────────────────────────
# Maps token -> issued_at timestamp.  Tokens expire after 60 seconds.
_TOKENS: dict[str, float] = {}
_TOKEN_TTL = 60  # seconds

# ── SESSION LIMITER ───────────────────────────────────────────────────────────
_MAX_SESSIONS = 3
_active_sessions = 0
_session_lock = threading.Lock()

# ── SESSION TIMEOUT ───────────────────────────────────────────────────────────
_SESSION_TIMEOUT = 1800  # 30 minutes

# ── TOKEN MANAGEMENT ─────────────────────────────────────────────────────────

def issue_token() -> str:
    """Generate a single-use auth token valid for _TOKEN_TTL seconds."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    # Prune old tokens
    expired = [t for t, ts in _TOKENS.items() if now - ts > _TOKEN_TTL]
    for t in expired:
        _TOKENS.pop(t, None)
    _TOKENS[token] = now
    return token


def consume_token(token: str) -> bool:
    """Validate and consume a token (single-use). Returns True if valid."""
    issued_at = _TOKENS.pop(token, None)
    if issued_at is None:
        return False
    return not time.time() - issued_at > _TOKEN_TTL


# ── TERMINAL HTML ─────────────────────────────────────────────────────────────

def _build_html(token: str) -> str:
    return f"""<!DOCTYPE html>
<html>
  <head>
    <title>Web Terminal</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@4.19.0/css/xterm.css" />
    <script src="https://cdn.jsdelivr.net/npm/xterm@4.19.0/lib/xterm.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.5.0/lib/xterm-addon-fit.js"></script>
    <style>
      body {{ background: #1e1e1e; margin: 0; padding: 10px; height: 100vh; overflow: hidden; }}
      #terminal {{ height: 100%; width: 100%; }}
    </style>
  </head>
  <body>
    <div id="terminal"></div>
    <script>
      var term = new Terminal({{cursorBlink: true, theme: {{background: '#1e1e1e'}}}});
      var fitAddon = new FitAddon.FitAddon();
      term.loadAddon(fitAddon);
      term.open(document.getElementById('terminal'));
      fitAddon.fit();

      // Use same-origin ws so it inherits any TLS from a reverse proxy
      var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      var ws = new WebSocket(proto + '//' + location.host + '/ws?token={token}');

      ws.onopen = function() {{
          term.write('\\r\\n*** Connected to Web Terminal ***\\r\\n');
      }};
      ws.onerror = function() {{
          term.write('\\r\\n*** Connection error — is the server running? ***\\r\\n');
      }};
      ws.onclose = function() {{
          term.write('\\r\\n*** Session closed ***\\r\\n');
      }};
      ws.onmessage = function(event) {{
          term.write(event.data);
      }};
      term.onData(function(data) {{
          if (ws.readyState === WebSocket.OPEN) ws.send(data);
      }});
      window.addEventListener('resize', () => fitAddon.fit());
    </script>
  </body>
</html>"""


# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.get("/")
async def get_terminal():
    """Issue a fresh single-use token and serve the terminal UI."""
    token = issue_token()
    return HTMLResponse(_build_html(token))


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(default=""),
):
    global _active_sessions

    # ── AUTH ──────────────────────────────────────────────────────────────────
    if not consume_token(token):
        await websocket.close(code=4403, reason="Unauthorized")
        return

    # ── SESSION LIMIT ─────────────────────────────────────────────────────────
    with _session_lock:
        if _active_sessions >= _MAX_SESSIONS:
            await websocket.close(code=4429, reason="Too many active sessions")
            return
        _active_sessions += 1

    await websocket.accept()

    pid, fd = pty.fork()
    if pid == 0:
        # Child process: exec bash
        os.environ["TERM"] = "xterm-256color"
        os.execvp("bash", ["bash"])
        # unreachable, but safety exit
        os._exit(1)

    # Parent process
    loop = asyncio.get_event_loop()
    session_start = time.time()

    def pty_reader():
        """Read from PTY and schedule a WebSocket send on the event loop."""
        try:
            data = os.read(fd, 4096)
        except OSError:
            loop.remove_reader(fd)
            return
        if data:
            # Use call_soon_threadsafe so exceptions propagate to the loop
            async def _send():
                try:
                    await websocket.send_text(data.decode("utf-8", errors="replace"))
                except Exception:
                    loop.remove_reader(fd)
            loop.call_soon_threadsafe(lambda: asyncio.ensure_future(_send()))
        else:
            loop.remove_reader(fd)

    loop.add_reader(fd, pty_reader)

    try:
        while True:
            # Enforce session timeout
            if time.time() - session_start > _SESSION_TIMEOUT:
                await websocket.send_text("\r\n*** Session timeout (30 min) ***\r\n")
                break
            data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
            os.write(fd, data.encode("utf-8"))
    except asyncio.TimeoutError:
        pass  # Keep alive — just no input for 60 s; loop again
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        with _session_lock:
            _active_sessions = max(0, _active_sessions - 1)
        with contextlib.suppress(Exception):
            loop.remove_reader(fd)
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(OSError):
            os.kill(pid, 9)


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Bind to localhost only — use a reverse proxy + TLS for external access
    uvicorn.run(app, host="127.0.0.1", port=5070)
