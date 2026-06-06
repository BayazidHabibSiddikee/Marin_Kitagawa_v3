import os
import re
import json
import asyncio
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import threading

from bayazid import (
    main as bayazid_main,
    teach_topic, generate_quiz, create_study_plan,
    review_code, explain_error,
    handle_timer_command, format_study_context,
    timer, memory
)
from marin import main as marin_main, format_game_context_for_marin
from arena import (
    build_marin_arena_prompt as build_marin__prompt,
    build_bayazid_arena_prompt as build_bayazid__prompt,
    _stream_debate, _stream_judge,
    _load_arena_history as _load__history,
    _load_bayazid_history, _format_history_for_context,
)
from classifier import classify, extract_timer_task, extract_topic, extract_quiz_params
from config import UPLOAD_FOLDER, HOST, PORT

app = FastAPI(title=" HS-02")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("static/generated", exist_ok=True)

ACTIVE_AGENT = "bayazid"


# ── PAGE ROUTES ───────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/chat", response_class=HTMLResponse)
async def get_chat(request: Request, agent: str = "bayazid"):
    global ACTIVE_AGENT
    ACTIVE_AGENT = agent
    return templates.TemplateResponse(request=request, name="bayazid_chat.html", context={"agent": agent})

@app.get("/profile", response_class=HTMLResponse)
async def get_profile(request: Request):
    return templates.TemplateResponse(request=request, name="profile.html")


# ── UPLOAD ────────────────────────────────────────────────────────────────

@app.post("/upload")
async def upload_image(image: UploadFile = File(...)):
    if not image.filename:
        return JSONResponse({"error": "No filename"}, status_code=400)
    filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', image.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    with open(filepath, "wb") as buf:
        buf.write(await image.read())
    return {"ok": True, "path": f"/{filepath}"}


# ── MAIN CHAT ENDPOINT ────────────────────────────────────────────────────

@app.post("/message")
async def handle_message(
    message: str = Form(...),
    image: UploadFile = File(None),
    study_context: str = Form(None)
):
    image_path = None
    if image and image.filename:
        filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', image.filename)
        image_path = os.path.join(UPLOAD_FOLDER, filename)
        with open(image_path, "wb") as buf:
            buf.write(await image.read())
        image_path = os.path.abspath(image_path)

    if ACTIVE_AGENT == "marin":
        from games.tiktaktoe import get_game
        game = get_game()
        state = game.get_board_state() if game else None
        game_context = format_game_context_for_marin(state) if state else None
        return StreamingResponse(
            marin_main(message, image_path=image_path, game_context=game_context),
            media_type="text/plain"
        )

    clf = classify(message)
    intent = clf["intent"]
    sub = clf.get("sub_intent")

    # Route by intent
    if intent == "timer":
        task = extract_timer_task(message)
        result = await handle_timer_command(sub or "status", task)
        async def timer_stream():
            yield result
        return StreamingResponse(timer_stream(), media_type="text/plain")

    elif intent == "teach":
        topic = extract_topic(message)
        depth = sub or "standard"
        return StreamingResponse(teach_topic(topic, depth), media_type="text/plain")

    elif intent == "study_plan":
        topic = extract_topic(message)
        return StreamingResponse(create_study_plan(topic), media_type="text/plain")

    elif intent == "code_review":
        code_match = re.search(r'```[\w]*\n?([\s\S]+?)```', message)
        code = code_match.group(1) if code_match else message
        return StreamingResponse(review_code(code), media_type="text/plain")

    elif intent == "debug":
        error_match = re.search(r'```[\w]*\n?([\s\S]+?)```', message)
        error_text = error_match.group(1) if error_match else message
        return StreamingResponse(explain_error(error_text), media_type="text/plain")

    else:
        ctx = format_study_context(json.loads(study_context)) if study_context else None
        return StreamingResponse(
            bayazid_main(message, image_path=image_path, study_context=ctx),
            media_type="text/plain"
        )


# ── QUIZ ENDPOINT (streams the quiz as plain text) ───────────────────────

@app.post("/quiz/generate")
async def generate_quiz_endpoint(
    topic: str = Form(...),
    difficulty: str = Form("medium"),
    num_questions: int = Form(5)
):
    return StreamingResponse(
        generate_quiz(topic, difficulty, num_questions),
        media_type="text/plain"
    )


# ── TIMER API ─────────────────────────────────────────────────────────────

@app.post("/timer/{command}")
async def timer_command(command: str, task: str = Form("")):
    result = await handle_timer_command(command, task)
    return JSONResponse({"message": result, "stats": timer.get_stats()})

@app.get("/timer/stats")
async def get_timer_stats():
    return JSONResponse(timer.get_stats())


# ── MEMORY MANAGEMENT ─────────────────────────────────────────────────────

@app.post("/memory/clear")
async def clear_memory():
    if ACTIVE_AGENT == "marin":
        return JSONResponse({"ok": True, "message": "Marin memory cannot be cleared via this endpoint."})
    memory.clear()
    return JSONResponse({"ok": True, "message": "Memory cleared."})


# ── AGENT SWITCHING ──────────────────────────────────────────────────────────

@app.post("/agent/switch")
async def switch_agent(agent: str = Form(...)):
    global ACTIVE_AGENT
    ACTIVE_AGENT = agent
    return {"ok": True, "agent": agent}


# ── AUDIO STOP (interrupt TTS speech) ─────────────────────────────────────────

@app.post("/audio/stop")
async def audio_stop():
    import marin
    killed = marin.stop_audio()
    return {"ok": True, "killed": killed}


# ── SETTINGS (shared by Marin) ───────────────────────────────────────────────

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

@app.get("/settings/maxtokens")
async def get_maxtokens():
    import marin
    return {"max_tokens": marin.MAX_TOKENS}

@app.post("/settings/maxtokens")
async def set_maxtokens(tokens: int = Form(...)):
    import marin
    marin.MAX_TOKENS = max(0, min(tokens, 4096))
    return {"max_tokens": marin.MAX_TOKENS}


# ── ARENA DEBATE ROUTES ─────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def get_(request: Request):
    return templates.TemplateResponse(request=request, name="_chat.html")


@app.post("/arena/stream")
async def _stream(request: Request):
    body        = await request.json()
    character   = body.get("character", "marin")
    topic       = body.get("topic", "")
    context     = body.get("context", "")
    marin_arg   = body.get("marin_arg", "")
    bayazid_arg = body.get("bayazid_arg", "")

    marin_hist_ctx   = ""
    bayazid_hist_ctx = ""

    if character in ("marin", "judge"):
        marin_hist  = await asyncio.to_thread(_load__history, 20)
        marin_hist_ctx = _format_history_for_context(marin_hist, "Marin")

    if character in ("bayazid", "judge"):
        bayazid_hist    = await asyncio.to_thread(_load_bayazid_history, 20)
        bayazid_hist_ctx = _format_history_for_context(bayazid_hist, "")

    marin_system   = build_marin__prompt(marin_hist_ctx)
    bayazid_system = build_bayazid__prompt(bayazid_hist_ctx)

    queue = asyncio.Queue()
    loop  = asyncio.get_event_loop()

    def run_in_thread():
        try:
            if character == "marin":
                gen = _stream_debate(marin_system, f'Argue your perspective on this topic: "{topic}"', context)
            elif character == "bayazid":
                gen = _stream_debate(bayazid_system, f'Argue your perspective on this topic: "{topic}"', context)
            elif character == "judge":
                gen = _stream_judge(topic, marin_arg, bayazid_arg)
            else:
                loop.call_soon_threadsafe(queue.put_nowait, "[ERROR] Unknown character")
                loop.call_soon_threadsafe(queue.put_nowait, None)
                return
            for chunk in gen:
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, f"[ERROR] {str(e)}")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=run_in_thread, daemon=True).start()

    async def generate():
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

    return StreamingResponse(generate(), media_type="text/plain")


@app.post("/arena/stream/live")
async def _stream_live(request: Request):
    return await _stream(request)


@app.get("/arena/history")
async def _history(limit: int = 10):
    marin_hist   = await asyncio.to_thread(_load__history,   limit)
    bayazid_hist = await asyncio.to_thread(_load_bayazid_history, limit)
    return {"marin": marin_hist, "bayazid": bayazid_hist}


# ── COMMAND LOG (Marin tool execution log) ────────────────────────────────────

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


# ── MEMORY (agent-aware) ──────────────────────────────────────────────────────

@app.get("/memory/status")
async def memory_status():
    if ACTIVE_AGENT == "marin":
        from marin import load_history
        messages = load_history(limit=60)
    else:
        messages = memory.get()
    return {"messages": messages}


# ── HEALTH ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "operational", "codename": "BAYAZID HS-02"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
