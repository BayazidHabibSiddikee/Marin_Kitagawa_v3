from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime, date

app = Flask(__name__)
DB = "todos.db"


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category_id INTEGER,
            status TEXT DEFAULT 'todo',
            priority TEXT DEFAULT 'medium',
            created_at TEXT DEFAULT (date('now')),
            completed_at TEXT,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
        );
    """)
    db.commit()
    db.close()


# ---- Page routes ----

@app.route("/")
def index():
    return render_template("index.html")


# ---- Todo CRUD ----

@app.route("/api/todos", methods=["GET"])
def list_todos():
    db = get_db()
    todos = db.execute(
        "SELECT t.*, c.name as category_name FROM todos t "
        "LEFT JOIN categories c ON t.category_id = c.id ORDER BY t.id DESC"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in todos])


@app.route("/api/todos", methods=["POST"])
def create_todo():
    data = request.json
    db = get_db()
    category_id = data.get("category_id")
    db.execute(
        "INSERT INTO todos (title, category_id, priority) VALUES (?, ?, ?)",
        (data["title"], category_id or None, data.get("priority", "medium")),
    )
    db.commit()
    todo_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    todo = db.execute(
        "SELECT t.*, c.name as category_name FROM todos t "
        "LEFT JOIN categories c ON t.category_id = c.id WHERE t.id = ?",
        (todo_id,),
    ).fetchone()
    db.close()
    return jsonify(dict(todo)), 201


@app.route("/api/todos/<int:id>", methods=["PATCH"])
def update_todo(id):
    data = request.json
    db = get_db()
    fields = []
    values = []
    for key in ("title", "status", "priority", "category_id"):
        if key in data:
            fields.append(f"{key} = ?")
            values.append(data[key])
    if "status" in data and data["status"] == "done":
        fields.append("completed_at = ?")
        values.append(date.today().isoformat())
    if "status" in data and data["status"] != "done":
        fields.append("completed_at = NULL")
    values.append(id)
    db.execute(f"UPDATE todos SET {', '.join(fields)} WHERE id = ?", values)
    db.commit()
    todo = db.execute(
        "SELECT t.*, c.name as category_name FROM todos t "
        "LEFT JOIN categories c ON t.category_id = c.id WHERE t.id = ?",
        (id,),
    ).fetchone()
    db.close()
    return jsonify(dict(todo))


@app.route("/api/todos/<int:id>", methods=["DELETE"])
def delete_todo(id):
    db = get_db()
    db.execute("DELETE FROM todos WHERE id = ?", (id,))
    db.commit()
    db.close()
    return "", 204


# ---- Category CRUD ----

@app.route("/api/categories", methods=["GET"])
def list_categories():
    db = get_db()
    cats = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    db.close()
    return jsonify([dict(c) for c in cats])


@app.route("/api/categories", methods=["POST"])
def create_category():
    data = request.json
    db = get_db()
    try:
        db.execute("INSERT INTO categories (name) VALUES (?)", (data["name"],))
        db.commit()
        cat_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    except sqlite3.IntegrityError:
        existing = db.execute(
            "SELECT * FROM categories WHERE name = ?", (data["name"],)
        ).fetchone()
        db.close()
        return jsonify(dict(existing)), 200
    cat = db.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    db.close()
    return jsonify(dict(cat)), 201


# ---- Dashboard / Stats ----

@app.route("/api/stats", methods=["GET"])
def stats():
    db = get_db()

    # Overall counts by status
    status_data = db.execute(
        "SELECT status, COUNT(*) as count FROM todos GROUP BY status"
    ).fetchall()

    # Per-category progress
    cat_data = db.execute(
        "SELECT c.name, "
        "  COUNT(t.id) as total, "
        "  SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END) as done, "
        "  SUM(CASE WHEN t.status='in-progress' THEN 1 ELSE 0 END) as in_progress, "
        "  SUM(CASE WHEN t.status='todo' THEN 1 ELSE 0 END) as todo "
        "FROM categories c "
        "LEFT JOIN todos t ON c.id = t.category_id "
        "GROUP BY c.id ORDER BY c.name"
    ).fetchall()

    # Daily completion (last 7 days with entries)
    daily = db.execute(
        "SELECT completed_at, COUNT(*) as count FROM todos "
        "WHERE status = 'done' AND completed_at IS NOT NULL "
        "GROUP BY completed_at ORDER BY completed_at DESC LIMIT 7"
    ).fetchall()

    # Priority breakdown
    priority = db.execute(
        "SELECT priority, COUNT(*) as count FROM todos GROUP BY priority"
    ).fetchall()

    db.close()
    return jsonify({
        "status": {r["status"]: r["count"] for r in status_data},
        "categories": [dict(c) for c in cat_data],
        "daily_completion": [dict(d) for d in daily],
        "priority": {r["priority"]: r["count"] for r in priority},
    })


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
