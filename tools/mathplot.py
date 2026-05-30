#!/usr/bin/env python3
"""
Math Equation Plotter — parametric equation grapher using CNC Simulator

Usage:
  python maths/mathplot.py -x "r*cos(t)" -y "r*sin(t)"            # circle (explicit)
  python maths/mathplot.py -x "t" -y "t**2" -t0 -4 -t1 4         # parabola
  python maths/mathplot.py heart                                  # preset shape
  python maths/mathplot.py --list                                 # list presets
  python maths/mathplot.py heart --export heart_path.h            # export to C header
  python maths/mathplot.py "draw a heart"                         # NLP mode (Ollama)

Arguments:
  -x EXPR        X(t) parametric expression
  -y EXPR        Y(t) parametric expression
  -t0 VAL        t start (default: 0)
  -t1 VAL        t end (default: 2*pi for most presets)
  -n, --points N number of sample points (default: 300)
  -r, --radius R scale / radius factor (default: 10)
  --name STR     window title
  --delay F      draw delay in seconds (default: 0.01, lower = faster)
  --grid         show grid on canvas
  --list         list all preset shapes
  --export FILE  export coordinates to C header file
  -h, --help     show this help
"""

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

# ── SAFE EVAL ──────────────────────────────────────────────────────────────────
_SAFE_BUILTINS = {
    "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan,
    "sinh": np.sinh, "cosh": np.cosh, "tanh": np.tanh,
    "sqrt": np.sqrt, "exp": np.exp, "log": np.log, "log10": np.log10,
    "abs": np.abs, "arcsin": np.arcsin, "arccos": np.arccos, "arctan": np.arctan,
    "pi": np.pi, "e": np.e,
    "math": np,  # Alias math to numpy for convenience
    "np": np,
}
_SAFE_GLOBALS = {"__builtins__": {}}


def _eval_expr(expr: str, t: np.ndarray, r: float):
    # Support both ^ and **
    expr = expr.replace("^", "**")
    safe = {"t": t, "r": r, "np": np, **_SAFE_BUILTINS}
    val = eval(expr, _SAFE_GLOBALS, safe)
    if isinstance(val, (int, float)):
        val = np.full_like(t, val, dtype=float)
    return val


# ── CNC RENDER ─────────────────────────────────────────────────────────────────
def plot(
    x_expr: str, y_expr: str,
    t_start=0.0, t_end=2*np.pi, n_points=300, r=10.0,
    title="Math Plot", delay=0.01, grid=False, export=None,
):
    """Evaluate parametric expressions and animate on CNC simulator."""
    points = _compute_points(x_expr, y_expr, t_start, t_end, n_points, r)
    if export:
        _do_export(x_expr, y_expr, points, export)

    from CNC_simulation import CNC
    cnc = CNC(
        title=title, width=800, height=800,
        x_range=(-30, 30), y_range=(-30, 30),
        draw_delay=delay, grid=grid,
    )
    for i in range(len(points) - 1):
        cnc.segment(points[i], points[i + 1], color="blue", width=2)
    cnc.show()


def plot_sequence(plots, delay=0.01, grid=False):
    """Draw multiple parametric plots sequentially on the same CNC canvas,
    clearing between each."""
    import time
    from CNC_simulation import CNC

    titles = [p[6] for p in plots]
    cnc = CNC(
        title=" | ".join(titles[:4]) + (" ..." if len(titles) > 4 else ""),
        width=800, height=800,
        x_range=(-30, 30), y_range=(-30, 30),
        draw_delay=delay, grid=grid,
    )

    for i, (x_expr, y_expr, t_start, t_end, n_points, r, name) in enumerate(plots):
        print(f"Sequence {i+1}/{len(plots)}: {name}")
        points = _compute_points(x_expr, y_expr, t_start, t_end, n_points, r)

        if i > 0:
            time.sleep(0.5)
            cnc.clear()

        for j in range(len(points) - 1):
            cnc.segment(points[j], points[j + 1], color="blue", width=2)

    cnc.show()


def _compute_points(x_expr, y_expr, t_start, t_end, n_points, r):
    t_vals = np.linspace(t_start, t_end, n_points)
    xc = _eval_expr(x_expr, t_vals, r)
    yc = _eval_expr(y_expr, t_vals, r)
    if isinstance(xc, (int, float)):
        xc = np.full_like(t_vals, xc, dtype=float)
    if isinstance(yc, (int, float)):
        yc = np.full_like(t_vals, yc, dtype=float)
    return [(float(xc[i]), float(yc[i])) for i in range(len(t_vals))]


def _do_export(x_expr, y_expr, points, filename):
    from create_c_array import export_to_c_array
    xl = [p[0] for p in points]
    yl = [p[1] for p in points]
    zl = [0.0] * len(points)
    export_to_c_array(xl, yl, zl, filename)
    print(f"Exported {len(points)} points to {filename}")


# ── PRESET SHAPES ──────────────────────────────────────────────────────────────
# Each entry: (x_expr, y_expr, t_start, t_end, description)
PRESETS = {
    "circle":        ("r*cos(t)",            "r*sin(t)",                              0, 2*np.pi,       "Circle"),
    "heart":         ("16*sin(t)**3",         "13*cos(t)-5*cos(2*t)-2*cos(3*t)-cos(4*t)", 0, 2*np.pi, "Heart Curve"),
    "rose":          ("r*cos(5*t)*cos(t)",   "r*cos(5*t)*sin(t)",                      0, np.pi,         "Petal Rose (5-petal)"),
    "lissajous":     ("r*sin(t)",            "r*sin(2*t)",                             0, 2*np.pi,       "Lissajous Figure-8"),
    "butterfly":     ("r*sin(t)*(exp(cos(t))-2*cos(4*t)-sin(t/12)**5)",
                                             "r*cos(t)*(exp(cos(t))-2*cos(4*t)-sin(t/12)**5)", 0, 10*np.pi, "Butterfly Curve"),
    "spiral":        ("(r/10)*t*cos(t)",     "(r/10)*t*sin(t)",                        0, 8*np.pi,       "Archimedean Spiral"),
    "cardioid":      ("r*(1+cos(t))*cos(t)", "r*(1+cos(t))*sin(t)",                    0, 2*np.pi,       "Cardioid"),
    "astroid":       ("r*cos(t)**3",         "r*sin(t)**3",                            0, 2*np.pi,       "Astroid"),
    "epitrochoid":   ("(r+r/3)*cos(t)-(r/2)*cos(4*t)",
                                             "(r+r/3)*sin(t)-(r/2)*sin(4*t)",          0, 2*np.pi,       "Epitrochoid"),
    "hypotrochoid":  ("(r-r/4)*cos(t)+(r/2)*cos(3*t)",
                                             "(r-r/4)*sin(t)-(r/2)*sin(3*t)",          0, 2*np.pi,       "Hypotrochoid"),
    "cycloid":       ("r*(t-sin(t))",        "r*(1-cos(t))",                           0, 4*np.pi,       "Cycloid"),
    "deltoid":       ("r*(2*cos(t)+cos(2*t))", "r*(2*sin(t)-sin(2*t))",                0, 2*np.pi,       "Deltoid"),
    "lemniscate":    ("r*cos(t)/(1+sin(t)**2)", "r*sin(t)*cos(t)/(1+sin(t)**2)",       0, 2*np.pi,       "Lemniscate of Bernoulli"),
    "sine":          ("t",                    "r*sin(3*t)",                            -10, 10,           "Sine Wave (3 freq)"),
    "parabola":      ("t",                    "t**2",                                  -4, 4,             "Parabola y = x²"),
    "logspiral":     ("(r/20)*exp(0.2*t)*cos(t)", "(r/20)*exp(0.2*t)*sin(t)",           0, 4*np.pi,       "Logarithmic Spiral"),
    "infinity":      ("r*sin(t)",             "r*sin(t)*cos(t)/(1+sin(t)**2)",          0, 2*np.pi,       "Infinity Symbol"),
    "witch":         ("r*t",                  "8*r**3/(t**2+4*r**2)",                  -4, 4,             "Witch of Agnesi"),
    "star":          ("r*cos(t)*(1+0.3*cos(5*t))",
                                             "r*sin(t)*(1+0.3*cos(5*t))",              0, 2*np.pi,       "5-point Star"),
    "rainbow":       ("(r/3)*t*cos(t)",      "(r/3)*t*sin(t)",                         0, 12*np.pi,      "Rainbow Spiral"),
    "hexagon":       ("r*0.8660254*cos(t)/cos(t-(t//1.04719755)*1.04719755-0.52359878)",
                                             "r*0.8660254*sin(t)/cos(t-(t//1.04719755)*1.04719755-0.52359878)", 0, 2*np.pi, "Hexagon"),
    "square":        ("r*0.7071068*cos(t)/cos(t-(t//1.57079633)*1.57079633-0.78539816)",
                                             "r*0.7071068*sin(t)/cos(t-(t//1.57079633)*1.57079633-0.78539816)", 0, 2*np.pi, "Square"),
    "triangle":      ("r*0.5*cos(t)/cos(t-(t//2.0943951)*2.0943951-1.04719755)",
                                             "r*0.5*sin(t)/cos(t-(t//2.0943951)*2.0943951-1.04719755)", 0, 2*np.pi, "Triangle"),
    "pentagon":      ("r*0.80901699*cos(t)/cos(t-(t//1.25663706)*1.25663706-0.62831853)",
                                             "r*0.80901699*sin(t)/cos(t-(t//1.25663706)*1.25663706-0.62831853)", 0, 2*np.pi, "Pentagon"),
}


def list_presets():
    print("Available preset shapes:")
    print(f"  {'Name':<20} {'Description'}")
    print(f"  {'-'*20} {'-'*30}")
    for name, (_, _, _, _, desc) in sorted(PRESETS.items()):
        print(f"  {name:<20} {desc}")


# ── OLLAMA NLP PARSER (from main_auto.py) ────────────────────────────────────
_SYSTEM_PROMPT = """\
You are a CNC math parser. Convert user input to parametric equations with parameter t.

RULES:
1. Return ONLY valid JSON (no markdown, no explanation):
   {"x_expr": "expression for x(t)", "y_expr": "expression for y(t)", "t_start": 0, "t_end": 6.28, "n_points": 300, "r": 10}
2. Use Python syntax: t**2 (not t^2), math functions: sin(t), cos(t), sqrt(t), exp(t), pi, abs(t)
3. Examples:
   - "y = x^2" -> {"x_expr": "t", "y_expr": "t**2", "t_start": -4, "t_end": 4, "n_points": 300, "r": 10}
   - "x = y^2 + 5" -> {"x_expr": "t**2 + 5", "y_expr": "t", "t_start": 0, "t_end": 6.28, "n_points": 300, "r": 10}
   - "circle radius 5" -> {"x_expr": "5*cos(t)", "y_expr": "5*sin(t)", "t_start": 0, "t_end": 6.28, "n_points": 300, "r": 5}
   - "draw a heart" -> {"x_expr": "16*sin(t)**3", "y_expr": "13*cos(t)-5*cos(2*t)-2*cos(3*t)-cos(4*t)", "t_start": 0, "t_end": 6.28, "n_points": 300, "r": 10}
4. If NOT a draw request, reply exactly: NOT_DRAW
5. NO code blocks, NO explanations, ONLY the JSON or NOT_DRAW.
"""


def _ollama_parse(text: str) -> dict | None:
    try:
        import ollama
        resp = ollama.chat(
            model="qwen2.5:0.5b",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        raw = resp.message.content if hasattr(resp, "message") else resp["message"]["content"]
        if "NOT_DRAW" in raw:
            return None
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return json.loads(cleaned)
    except Exception as e:
        print(f"[NLP] Ollama parse failed: {e}", file=sys.stderr)
        return None


def _parse_simple_equation(text: str) -> dict | None:
    """Fallback regex parser for equations like 'y = x^2' or 'x = y^2 + 5'."""
    text = text.strip().lower()
    m = re.match(r"^\s*([xy])\s*=\s*(.+?)\s*$", text)
    if not m:
        return None
    dep, expr = m.group(1), m.group(2).strip()
    expr = re.sub(r"\^", "**", expr)
    if not re.match(r"^[xy\d\+\-\*\/\(\)\.\s\*\*]+$", expr):
        return None
    if dep == "y":
        return {"x_expr": "t", "y_expr": expr.replace("x", "t"), "t_start": 0, "t_end": 6.28, "n_points": 300, "r": 10}
    else:
        return {"x_expr": expr.replace("y", "t"), "y_expr": "t", "t_start": 0, "t_end": 6.28, "n_points": 300, "r": 10}


def _validate_exprs(data: dict) -> bool:
    return bool(data.get("x_expr", "").strip() and data.get("y_expr", "").strip())


def _try_nlp(text: str) -> dict | None:
    # Presets first — deterministic, no LLM needed
    key = text.strip().lower().replace(" ", "_")
    if key in PRESETS:
        x_expr, y_expr, t0, t1, desc = PRESETS[key]
        return {"x_expr": x_expr, "y_expr": y_expr, "t_start": t0, "t_end": t1, "n_points": 300, "r": 10, "name": desc}

    # Regex fallback for equations like "y = x^2"
    fallback = _parse_simple_equation(text)
    if fallback:
        return fallback

    # Last resort: Ollama NLP (unreliable, validate output)
    data = _ollama_parse(text)
    if data and _validate_exprs(data):
        return data
    return None


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Math Equation Plotter — parametric equation grapher using CNC Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python maths/mathplot.py -x \"r*cos(t)\" -y \"r*sin(t)\"\n"
            "  python maths/mathplot.py -x t -y \"t**2\" -t0 -4 -t1 4\n"
            "  python maths/mathplot.py heart\n"
            "  python maths/mathplot.py \"draw a butterfly\"\n"
            "  python maths/mathplot.py heart butterfly spiral   (sequence)\n"
            "  python maths/mathplot.py --list\n"
        ),
    )
    parser.add_argument("input", nargs="*", help="Preset shape name(s), equation text, or NLP query. Multiple = sequence.")
    parser.add_argument("-x", metavar="EXPR", help="X(t) parametric expression")
    parser.add_argument("-y", metavar="EXPR", help="Y(t) parametric expression")
    parser.add_argument("-t0", type=float, help="t start (default: 0)")
    parser.add_argument("-t1", type=float, help="t end (default: 2*pi for most presets)")
    parser.add_argument("-n", "--points", type=int, default=300, help="number of sample points (default: 300)")
    parser.add_argument("-r", "--radius", type=float, default=10, help="radius/scale factor (default: 10)")
    parser.add_argument("--name", default="Math Plot", help="CNC window title")
    parser.add_argument("--delay", type=float, default=0.01, help="draw delay seconds (default: 0.01)")
    parser.add_argument("--grid", action="store_true", help="show grid on canvas")
    parser.add_argument("--list", action="store_true", help="list all preset shapes")
    parser.add_argument("--export", metavar="FILE", help="export coordinates to C header file")

    args = parser.parse_args()

    # --list
    if args.list:
        list_presets()
        return

    text = " ".join(args.input) if args.input else ""

    # ── Detect multi-graph sequence ───────────────────────────────────────────
    # Split by comma, then check if every word is a standalone preset
    parts = [p.strip() for p in re.split(r'\s*[,;]\s*', text) if p.strip()]
    words = text.split()
    if len(words) > 1 and all(w.lower() in PRESETS for w in words):
        parts = words  # space-separated presets = sequence

    if len(parts) > 1:
        sequence = []
        for part in parts:
            r2 = _try_nlp(part)
            if r2:
                sequence.append((
                    r2["x_expr"], r2["y_expr"],
                    r2.get("t_start", 0), r2.get("t_end", 2*np.pi),
                    r2.get("n_points", 300), r2.get("r", args.radius),
                    r2.get("name", "Graph"),
                ))
        if len(sequence) > 1:
            print(f"Plotting sequence of {len(sequence)} graphs...")
            for i, s in enumerate(sequence):
                print(f"  {i+1}. {s[6]}: x={s[0]}, y={s[1]}")
            plot_sequence(sequence, args.delay, args.grid)
            return

    # ── Single graph ──────────────────────────────────────────────────────────
    x_expr, y_expr = args.x, args.y
    t_start, t_end = args.t0, args.t1
    n_points = args.points
    r = args.radius
    title = args.name

    if x_expr and y_expr:
        if t_start is None: t_start = 0
        if t_end is None:   t_end = 2 * np.pi

    elif text:
        result = _try_nlp(text)
        if result is None:
            print(f"Could not parse '{text}' as a drawing request.", file=sys.stderr)
            print("Try --list for presets, or use -x/-y explicitly.", file=sys.stderr)
            sys.exit(1)
        x_expr = result["x_expr"]
        y_expr = result["y_expr"]
        t_start = result.get("t_start", t_start if t_start is not None else 0)
        t_end   = result.get("t_end",   t_end   if t_end   is not None else 2*np.pi)
        n_points = result.get("n_points", n_points)
        r       = result.get("r", r)
        title   = result.get("name", title)

    else:
        parser.print_help()
        sys.exit(1)

    if t_start is None: t_start = 0
    if t_end   is None: t_end   = 2 * np.pi

    print(f"Plotting: x(t)={x_expr}, y(t)={y_expr}")
    print(f"  t: [{t_start}, {t_end}], {n_points} points, r={r}")
    plot(x_expr, y_expr, t_start, t_end, n_points, r, title, args.delay, args.grid, args.export)


if __name__ == "__main__":
    main()
