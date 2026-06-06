import os
import re
import random
import asyncio
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import ollama
from marin import main as marin_main, format_game_context_for_marin
from bayazid import main as bayazid_main

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('static/generated', exist_ok=True)

ACTIVE_AGENT = "bayazid"

# ── TIC TAC TOE GAME ENGINE (Runs in RAM, no GUI needed) ─────────────────────
class GameSession:
    def __init__(self):
        self.reset()

    def reset(self):
        self.board = {str(i): None for i in range(1, 10)}
        self.turn = 'system' # 'O' goes first
        self.available = [str(i) for i in range(1, 10)]
        self.is_active = False
        self.log = []

    def get_board_str(self):
        rows = []
        for r in range(3):
            line = []
            for c in range(3):
                cell = str(r * 3 + c + 1)
                mark = self.board[cell]
                line.append(mark if mark else cell)
            rows.append(' | '.join(line))
        return "\n---------\n".join(rows)

    def make_move(self, cell, mark):
        if cell in self.available:
            self.available.remove(cell)
            self.board[cell] = mark
            self.turn = 'user' if mark == 'O' else 'system'

game = GameSession()

def check_winner(board):
    combos = [['1','2','3'],['4','5','6'],['7','8','9'],
              ['1','4','7'],['2','5','8'],['3','6','9'],
              ['1','5','9'],['3','5','7']]
    for c in combos:
        if board[c[0]] and board[c[0]] == board[c[1]] == board[c[2]]:
            return board[c[0]]
    return None

async def get_ai_move(g: GameSession):
    """Uses the main model or a tiny fast model in background."""
    if not g.available: return None
    board_str = g.get_board_str()
    available_str = ", ".join(g.available)
    prompt = (
        f"You are playing Tic Tac Toe as 'O'. Opponent is 'X'.\n"
        f"Board:\n{board_str}\nAvailable: {available_str}\n"
        f"Respond with ONLY a single digit from 1-9."
    )
    try:
        res = await asyncio.to_thread(
            ollama.chat, model="qwen2.5:0.5b", 
            messages=[{"role": "user", "content": prompt}],
            options={"num_predict": 5} # Super fast, only needs 1 character
        )
        match = re.search(r'[1-9]', res["message"]["content"])
        if match and match.group() in g.available:
            return match.group()
    except Exception as e:
        print(f"[Game AI Error] {e}")
    
    return random.choice(g.available) if g.available else None

# ── WEB ROUTES ────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/chat", response_class=HTMLResponse)
async def get_chat(request: Request, agent: str = "bayazid"):
    global ACTIVE_AGENT
    ACTIVE_AGENT = agent
    return templates.TemplateResponse(request=request, name="bayazid_chat.html", context={"agent": agent})

@app.post("/agent/switch")
async def switch_agent(agent: str = Form(...)):
    global ACTIVE_AGENT
    ACTIVE_AGENT = agent
    return {"ok": True, "agent": agent}

@app.post("/upload")
async def upload_image(image: UploadFile = File(...)):
    if not image.filename: return {"error": "No filename"}, 400
    filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', image.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    with open(filepath, "wb") as buf:
        buf.write(await image.read())
    return {"ok": True, "path": f"/{filepath}"}

@app.post("/message")
async def handle_message(message: str = Form(...), image: UploadFile = File(None)):
    image_path = None
    if image and image.filename:
        filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', image.filename)
        image_path = os.path.join(UPLOAD_FOLDER, filename)
        with open(image_path, "wb") as buf:
            buf.write(await image.read())
        image_path = os.path.abspath(image_path)

    # Pass the active game log to Marin so she knows the board state!
    game_context = "\n".join(game.log) if game.is_active else None

    if ACTIVE_AGENT == "marin":
        return StreamingResponse(
            marin_main(message, image_path=image_path, game_context=game_context), 
            media_type="text/plain"
        )
    else:
        #  main: (user_message, image_path=None, study_context=None, use_rag=True)
        return StreamingResponse(
            bayazid_main(message, image_path=image_path),
            media_type="text/plain"
        )

# ── GAME ROUTES ───────────────────────────────────────────────────────────────
@app.post("/game/start")
async def start_game():
    game.reset()
    game.is_active = True
    game.log.append("GAME STARTED: User is X, Marin is O.")
    
    ai_cell = await get_ai_move(game)
    if ai_cell:
        game.make_move(ai_cell, 'O')
        game.log.append(f"MARIN placed 'O' at cell {ai_cell}.")
    
    return {"board": game.board, "turn": game.turn, "log": game.log[-2:]}

from games.tiktaktoe import get_game

@app.get("/game/tiktaktoe/state")
async def get_tiktaktoe_state():
    """Get current game state"""
    game = get_game()
    return game.get_board_state()

@app.post("/game/tiktaktoe/move")
async def make_tiktaktoe_move(cell: str):
    """Make a user move and get marin's reaction"""
    game = get_game()
    
    if cell not in game.available or game.turn != "user":
        return {"error": "Invalid move"}
    
    # Convert cell to coordinates (simulate click)
    x, y = game.cell_center[cell]
    game.user_move(x, y)
    
    # Get updated state
    state = game.get_board_state()
    game_context = format_game_context_for_marin(state)
    
    # Get marin's reaction
    reaction = ""
    if game_context:
        async for chunk in marin_main("react to the game", game_context=game_context):
            if not chunk.startswith("__VIBE__"):
                reaction += chunk
    
    return {
        "state": state,
        "reaction": reaction
    }

@app.post("/game/tiktaktoe/ai-move")
async def trigger_ai_move():
    """Trigger AI move and get reaction"""
    game = get_game()
    
    if game.turn != "system":
        return {"error": "Not AI's turn"}
    
    game.system_move()
    state = game.get_board_state()
    game_context = format_game_context_for_marin(state)
    
    reaction = ""
    if game_context:
        async for chunk in marin_main("react to my move", game_context=game_context):
            if not chunk.startswith("__VIBE__"):
                reaction += chunk
    
    return {
        "state": state,
        "reaction": reaction
    }

@app.get("/memory/status")
async def memory_status():
    if ACTIVE_AGENT == "marin":
        from marin import load_history
    else:
        from bayazid import load_history
    messages = load_history(limit=60)
    return {"messages": messages}

@app.get("/settings/wordlimit")
async def get_wordlimit():
    import marin
    return {"word_limit": marin.WORD_LIMIT}

@app.post("/settings/wordlimit")
async def set_wordlimit(limit: int = Form(...)):
    import marin
    marin.WORD_LIMIT = max(0, limit)
    return {"word_limit": marin.WORD_LIMIT}

@app.get("/settings/voice")
async def get_voice():
    import marin
    return {"voice_enabled": marin.VOICE_ENABLED}

@app.post("/settings/voice")
async def set_voice(enabled: str = Form(...)):
    import marin
    marin.VOICE_ENABLED = enabled in ("1", "true", "True", "yes")
    return {"voice_enabled": marin.VOICE_ENABLED}

@app.get("/cmd/log")
async def cmd_log_page(request: Request):
    try:
        from marin_fier import _cmd_log
        logs = list(reversed(_cmd_log))
    except ImportError:
        logs = []
    return templates.TemplateResponse(request=request, name="terminal_log.html",
                                      context={"logs": logs})

@app.get("/cmd/log/json")
async def cmd_log_json(limit: int = 100):
    try:
        from marin_fier import _cmd_log
        logs = list(reversed(_cmd_log))
        if limit > 0:
            logs = logs[:limit]
        return {"logs": logs}
    except ImportError:
        return {"logs": []}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5069)