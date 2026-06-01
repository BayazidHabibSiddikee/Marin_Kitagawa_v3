import telebot
import new
import numpy as np
import re
import ollama
import json

# --- CONFIGURATION ---
API = "8690254124:AAG4hFS89yHbsEcNT3Wsfoa6io1jlVUAGgI"
bot = telebot.TeleBot(token=API)
OLLAMA_MODEL = "qwen2.5:0.5b"
ALLOWED_USERS = [8058658801]

# ── PRESET SHAPES (synced with mathplot.py) ────────────────────────────────────
PRESETS = {
    "circle":        ("r*cos(t)",            "r*sin(t)",                              0, 2*np.pi,       "Circle"),
    "heart":         ("16*sin(t)**3",         "13*cos(t)-5*cos(2*t)-2*cos(3*t)-cos(4*t)", 0, 2*np.pi, "Heart Curve"),
    "heart_curve":   ("16*sin(t)**3",         "13*cos(t)-5*cos(2*t)-2*cos(3*t)-cos(4*t)", 0, 2*np.pi, "Heart Curve"),
    "rose":          ("r*cos(5*t)*cos(t)",   "r*cos(5*t)*sin(t)",                      0, np.pi,       "Petal Rose"),
    "petal_rose":    ("r*cos(5*t)*cos(t)",   "r*cos(5*t)*sin(t)",                      0, np.pi,       "Petal Rose"),
    "lissajous":     ("r*sin(t)",            "r*sin(2*t)",                             0, 2*np.pi,     "Lissajous Figure-8"),
    "butterfly":     ("r*sin(t)*(exp(cos(t))-2*cos(4*t)-sin(t/12)**5)",
                                             "r*cos(t)*(exp(cos(t))-2*cos(4*t)-sin(t/12)**5)", 0, 10*np.pi, "Butterfly Curve"),
    "spiral":        ("(r/10)*t*cos(t)",     "(r/10)*t*sin(t)",                        0, 8*np.pi,     "Archimedean Spiral"),
    "cardioid":      ("r*(1+cos(t))*cos(t)", "r*(1+cos(t))*sin(t)",                    0, 2*np.pi,     "Cardioid"),
    "astroid":       ("r*cos(t)**3",         "r*sin(t)**3",                            0, 2*np.pi,     "Astroid"),
    "epitrochoid":   ("(r+r/3)*cos(t)-(r/2)*cos(4*t)",
                                             "(r+r/3)*sin(t)-(r/2)*sin(4*t)",          0, 2*np.pi,     "Epitrochoid"),
    "hypotrochoid":  ("(r-r/4)*cos(t)+(r/2)*cos(3*t)",
                                             "(r-r/4)*sin(t)-(r/2)*sin(3*t)",          0, 2*np.pi,     "Hypotrochoid"),
    "rhodonea":      ("r*cos(7*t)*cos(t)",   "r*cos(7*t)*sin(t)",                      0, np.pi,       "Rhodonea 7-petal"),
    "limacon":       ("r*(1+0.5*cos(t))*cos(t)", "r*(1+0.5*cos(t))*sin(t)",            0, 2*np.pi,     "Limacon"),
    "cycloid":       ("r*(t-sin(t))",        "r*(1-cos(t))",                           0, 4*np.pi,     "Cycloid"),
    "deltoid":       ("r*(2*cos(t)+cos(2*t))", "r*(2*sin(t)-sin(2*t))",                0, 2*np.pi,     "Deltoid"),
    "lemniscate":    ("r*cos(t)/(1+sin(t)**2)", "r*sin(t)*cos(t)/(1+sin(t)**2)",       0, 2*np.pi,     "Lemniscate"),
    "sine":          ("t",                    "r*sin(3*t)",                            -10, 10,         "Sine Wave"),
    "parabola":      ("t",                    "t**2",                                  -4, 4,           "Parabola"),
    "logspiral":     ("(r/20)*exp(0.2*t)*cos(t)", "(r/20)*exp(0.2*t)*sin(t)",           0, 4*np.pi,    "Logarithmic Spiral"),
    "logarithmic_spiral": ("(r/20)*exp(0.2*t)*cos(t)", "(r/20)*exp(0.2*t)*sin(t)",     0, 4*np.pi,    "Logarithmic Spiral"),
    "infinity":      ("r*sin(t)",             "r*sin(t)*cos(t)/(1+sin(t)**2)",          0, 2*np.pi,    "Infinity Symbol"),
    "star":          ("r*cos(t)*(1+0.3*cos(5*t))", "r*sin(t)*(1+0.3*cos(5*t))",        0, 2*np.pi,    "5-point Star"),
    "rainbow":       ("(r/3)*t*cos(t)",      "(r/3)*t*sin(t)",                         0, 12*np.pi,   "Rainbow Spiral"),
}

_NLP_KEYWORDS = {
    "heart": "heart", "love": "heart",
    "circle": "circle", "round": "circle",
    "rose": "rose", "flower": "rose", "petal": "rose",
    "lissajous": "lissajous", "figure eight": "lissajous", "figure-eight": "lissajous",
    "infinity": "infinity",
    "butterfly": "butterfly",
    "spiral": "spiral", "archimedean": "spiral",
    "cardioid": "cardioid",
    "astroid": "astroid",
    "epitrochoid": "epitrochoid",
    "hypotrochoid": "hypotrochoid",
    "rhodonea": "rhodonea",
    "limacon": "limacon",
    "cycloid": "cycloid",
    "deltoid": "deltoid",
    "lemniscate": "lemniscate", "bernoulli": "lemniscate",
    "sine": "sine", "sin wave": "sine", "sine wave": "sine",
    "parabola": "parabola",
    "log spiral": "logspiral", "logarithmic spiral": "logspiral",
    "star": "star",
    "rainbow": "rainbow",
}

# ── SAFE MATH EVAL ─────────────────────────────────────────────────────────────
_SAFE_MATH = {
    "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "sqrt": np.sqrt, "exp": np.exp, "log": np.log, "log10": np.log10,
    "abs": np.abs, "arcsin": np.arcsin, "arccos": np.arccos, "arctan": np.arctan,
    "pi": np.pi, "e": np.e,
}

def _eval_expr(expr, t, r=10.0):
    safe = {"t": t, "r": r, "np": np, **_SAFE_MATH}
    val = eval(expr, {"__builtins__": {}}, safe)
    if isinstance(val, (int, float)):
        val = np.full_like(t, float(val))
    return val

def _render(x_expr, y_expr, t_start, t_end, n_points, r, title):
    t = np.linspace(t_start, t_end, n_points)
    xc = _eval_expr(x_expr, t, r)
    yc = _eval_expr(y_expr, t, r)
    new.solution(xc, yc, t, title)

# ── NLP PIPELINE ───────────────────────────────────────────────────────────────
_SYSTEM_DRAW_PROMPT = """\
You are a CNC math parser. Convert user input to parametric equations with parameter t.

RULES:
1. Return ONLY valid JSON (no markdown, no explanation):
   {"x_expr": "...", "y_expr": "...", "t_start": 0, "t_end": 6.28, "n_points": 300, "r": 10}
2. Python syntax: t**2 (not t^2), functions: sin(t), cos(t), sqrt(t), exp(t), pi, abs(t)
3. Examples:
   - "y = x^2"         -> {"x_expr": "t", "y_expr": "t**2", "t_start": -4, "t_end": 4, "n_points": 300, "r": 10}
   - "circle radius 5" -> {"x_expr": "5*cos(t)", "y_expr": "5*sin(t)", "t_start": 0, "t_end": 6.28, "n_points": 300, "r": 5}
   - "draw a heart"    -> {"x_expr": "16*sin(t)**3", "y_expr": "13*cos(t)-5*cos(2*t)-2*cos(3*t)-cos(4*t)", "t_start": 0, "t_end": 6.28, "n_points": 300, "r": 10}
4. If NOT a draw request, reply exactly: NOT_DRAW
5. NO code blocks, NO explanations, ONLY the JSON or NOT_DRAW.
"""

def _ollama_parse(text):
    try:
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_DRAW_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        raw = resp.message.content if hasattr(resp, "message") else resp["message"]["content"]
        if "NOT_DRAW" in raw:
            return None
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        data = json.loads(cleaned)
        if data.get("x_expr", "").strip() and data.get("y_expr", "").strip():
            return data
    except Exception:
        pass
    return None

def _regex_parse(text):
    """Parse equations like y = x^2, y = sin(x)+1, x = t^2."""
    t = text.strip().lower()
    m = re.match(r"^\s*([xy])\s*=\s*(.+?)\s*$", t)
    if not m:
        return None
    dep, expr = m.group(1), m.group(2).strip()
    expr = re.sub(r"\^", "**", expr)
    if not re.match(r"^[xy\d\+\-\*\/\(\)\.\s\*\*sincotaqrexplogabspi]+$", expr):
        return None
    if dep == "y":
        return {"x_expr": "t", "y_expr": expr.replace("x", "t"), "t_start": -4, "t_end": 4, "n_points": 300, "r": 10}
    else:
        return {"x_expr": expr.replace("y", "t"), "y_expr": "t", "t_start": -4, "t_end": 4, "n_points": 300, "r": 10}

def _preset_lookup(text):
    key = text.strip().lower().replace(" ", "_")
    if key in PRESETS:
        x, y, t0, t1, desc = PRESETS[key]
        return {"x_expr": x, "y_expr": y, "t_start": t0, "t_end": t1, "n_points": 300, "r": 10, "name": desc}
    tl = text.strip().lower()
    for kw, pk in _NLP_KEYWORDS.items():
        if kw in tl:
            x, y, t0, t1, desc = PRESETS[pk]
            return {"x_expr": x, "y_expr": y, "t_start": t0, "t_end": t1, "n_points": 300, "r": 10, "name": desc}
    return None

def try_nlp(text):
    """Preset lookup → regex → Ollama."""
    return _preset_lookup(text) or _regex_parse(text) or _ollama_parse(text)

def ollama_respond(text):
    resp = ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": text}])
    return resp.message.content if hasattr(resp, "message") else resp["message"]["content"]

# ── SECURITY ───────────────────────────────────────────────────────────────────
def is_authorized(message):
    print(message.from_user.id)
    return message.from_user.id in ALLOWED_USERS

def get_params(text):
    parts = text.split()
    try:
        if len(parts) < 4:
            return None, "Format: `/shape X Y Radius`"
        return [float(i) for i in parts[1:4]], None
    except ValueError:
        return None, "Please use numbers for X, Y, and Radius."

# ── HANDLERS ───────────────────────────────────────────────────────────────────
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not is_authorized(message):
        bot.reply_to(message, "Access Denied. Your ID is not whitelisted.")
        return
    manual = (
        f"CNC Virtual Controller v4.0 (AI-Powered)\n\n"
        f"Welcome, {message.from_user.first_name}!\n\n"
        "1. Natural Language\n"
        "   Type: 'draw a heart', 'butterfly', 'y = x^2', 'circle radius 5'\n\n"
        "2. Manual Equation\n"
        "   /draw x_expr | y_expr | [points] | [t_start] | [t_end]\n"
        "   Example: /draw r*cos(t) | r*sin(t) | 200 | 0 | 6.28\n\n"
        "3. Preset Shapes\n"
        "   /circle, /heart, /butterfly, /spiral, /cardioid ...\n"
        "   Format: /shape X Y Radius\n\n"
        "4. Image Mode\n"
        "   Send a photo to auto-trace CNC paths."
    )
    bot.reply_to(message, manual)

@bot.message_handler(commands=['draw'])
def handle_free_draw(message):
    if not is_authorized(message): return
    parts_str = message.text.replace('/draw', '', 1).strip()
    parts = [p.strip() for p in parts_str.split('|')]
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /draw x_expr | y_expr | [points=300] | [t_start=0] | [t_end=2*pi]")
        return
    x_expr, y_expr = parts[0], parts[1]
    n_points = int(parts[2]) if len(parts) > 2 and parts[2] else 300
    _safe = {"__builtins__": {}, "pi": np.pi, "e": np.e}
    t_start = eval(parts[3], _safe) if len(parts) > 3 and parts[3] else 0
    t_end   = eval(parts[4], _safe) if len(parts) > 4 and parts[4] else 2*np.pi
    try:
        _render(x_expr, y_expr, t_start, t_end, n_points, 10, f"Custom: {x_expr}")
        bot.send_message(message.chat.id, f"Drew: x={x_expr}, y={y_expr}")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

ALL_SHAPES = list(PRESETS.keys())

@bot.message_handler(commands=ALL_SHAPES)
def handle_preset_command(message):
    if not is_authorized(message): return
    cmd = message.text.split()[0].replace('/', '').lower()
    params, error = get_params(message.text)
    if error:
        bot.reply_to(message, error)
        return
    x, y, r = params
    if cmd not in PRESETS:
        bot.reply_to(message, f"Unknown shape: {cmd}")
        return
    x_expr, y_expr, t0, t1, desc = PRESETS[cmd]
    bot.send_message(message.chat.id, f"Simulating {desc}...")
    try:
        _render(x_expr, y_expr, t0, t1, 300, r, desc)
        bot.send_message(message.chat.id, f"{desc} complete.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if not is_authorized(message): return
    bot.reply_to(message, "Image received! Converting to CNC paths...")
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open("input_image.jpg", 'wb') as f:
            f.write(downloaded_file)
        worker = new.Draw(0, 0, 15)
        worker.draw_cartoon("input_image.jpg")
        bot.send_message(message.chat.id, "Image trace complete!")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    if not is_authorized(message): return
    user_text = message.text.strip()
    if user_text.startswith('/'):
        bot.reply_to(message, "Unknown command. Use /help.")
        return

    bot.send_chat_action(message.chat.id, 'typing')
    data = try_nlp(user_text)

    if data:
        try:
            _render(
                data["x_expr"], data["y_expr"],
                data.get("t_start", 0), data.get("t_end", 2*np.pi),
                data.get("n_points", 300), data.get("r", 10),
                data.get("name", "Custom"),
            )
            bot.send_message(message.chat.id, f"Drew: {data.get('name', data['x_expr'])}")
            return
        except Exception as e:
            bot.reply_to(message, f"Draw error: {e}")
            return

    answer = ollama_respond(user_text)
    bot.reply_to(message, answer)

bot.polling()
