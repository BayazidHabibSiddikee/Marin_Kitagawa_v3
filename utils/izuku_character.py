#!/usr/bin/env python3
"""
izuku_character.py — Izuku Midoriya / Multi-Laws Wisdom merged character
BM25 + LangChain RAG · PostgreSQL-backed knowledge · TUI-ready

The character is a philosopher-scholar who:
  • Generates quotes, poetry, business ideas, philosophical connections
  • Merges Izuku's analytical notebook-taking with multi_laws_wisdom's universal laws
  • Operates via BM25 keyword retrieval + vector RAG on PostgreSQL
"""

import json
import os
import re
import sys
import time
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── PostgreSQL connection (lazy) ────────────────────────────────────────────────
_postgres_conn = None


def get_pg_conn():
    global _postgres_conn
    if _postgres_conn is not None:
        try:
            _postgres_conn.execute("SELECT 1")
            return _postgres_conn
        except Exception:
            _postgres_conn = None
    try:
        import psycopg2
        from config import load_settings
        s = load_settings()
        pg = s.get("postgresql", {})
        conn = psycopg2.connect(
            host=pg.get("host", "localhost"),
            port=pg.get("port", 5432),
            dbname=pg.get("dbname", "marin"),
            user=pg.get("user", "marin"),
            password=pg.get("password", ""),
            connect_timeout=5,
        )
        conn.autocommit = True
        _postgres_conn = conn
        return conn
    except Exception as e:
        print(f"[IzukuCharacter] PostgreSQL unavailable ({e}), falling back to SQLite")
        return None


def init_pg_schema():
    """Create the BM25 + tsvector tables if they don't exist."""
    conn = get_pg_conn()
    if conn is None:
        return False
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS izuku_knowledge (
            id          SERIAL PRIMARY KEY,
            category    TEXT NOT NULL DEFAULT 'general',
            title       TEXT NOT NULL,
            content     TEXT NOT NULL,
            source      TEXT DEFAULT 'manual',
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            updated_at  TIMESTAMPTZ DEFAULT NOW(),
            ts_vector   TSVECTOR
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_izuku_ts ON izuku_knowledge USING gin(ts_vector);
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS izuku_wisdom_quotes (
            id          SERIAL PRIMARY KEY,
            text        TEXT NOT NULL,
            author      TEXT DEFAULT 'Izuku-MultiLaws',
            theme       TEXT DEFAULT 'universal',
            source_law  TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS izuku_business_ideas (
            id          SERIAL PRIMARY KEY,
            title       TEXT NOT NULL,
            description TEXT NOT NULL,
            law_applied TEXT,
            feasibility TEXT DEFAULT 'medium',
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    # Trigger to auto-update tsvector
    cur.execute("""
        CREATE OR REPLACE FUNCTION update_izuku_tsvector() RETURNS trigger AS $$
        BEGIN
            NEW.ts_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.content, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    cur.execute("""
        DROP TRIGGER IF EXISTS izuku_tsvector_trigger ON izuku_knowledge;
    """)
    cur.execute("""
        CREATE TRIGGER izuku_tsvector_trigger
            BEFORE INSERT OR UPDATE ON izuku_knowledge
            FOR EACH ROW EXECUTE FUNCTION update_izuku_tsvector();
    """)
    conn.commit()
    cur.close()
    return True


# ── BM25 RANKING (pure Python, no sklearn needed) ─────────────────────────────

def _tokenize(text: str) -> list:
    return re.findall(r'[a-zA-Z0-9_]+', text.lower())


def _idf(doc_freqs: dict, total_docs: int) -> dict:
    return {term: ((total_docs - df + 0.5) / (df + 0.5) + 1).__log1p__()
            for term, df in doc_freqs.items()}


# Patch: use math.log instead
import math
def _bm25_idf(doc_freqs: dict, total_docs: int) -> dict:
    return {term: math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
            for term, df in doc_freqs.items()}


class BM25Retriever:
    """Pure-Python Okapi BM25 over a list of (title, content) tuples."""

    def __init__(self, documents: list[tuple[str, str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = documents
        self._build_index()

    def _build_index(self):
        self.num_docs = len(self.docs)
        self.avgdl = sum(len(d[1].split()) + len(d[0].split()) for d in self.docs) / max(self.num_docs, 1)
        freq = {}
        df = {}
        for title, content in self.docs:
            tokens = set(_tokenize(title + " " + content))
            tf = {}
            for t in _tokenize(title + " " + content):
                tf[t] = tf.get(t, 0) + 1
            freq[len(self.docs)] = tf
            for t in tokens:
                df[t] = df.get(t, 0) + 1
        self.tf = freq
        self.df = df
        self.idf = _bm25_idf(df, self.num_docs)

    def score(self, query: str, doc_idx: int) -> float:
        q_tokens = _tokenize(query)
        doc_tokens = _tokenize(self.docs[doc_idx][1])
        doc_len = len(doc_tokens)
        score = 0.0
        for q in q_tokens:
            if q not in self.df:
                continue
            tf = doc_tokens.count(q)
            idf = self.idf[q]
            num = tf * (self.k1 + 1)
            denom = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
            score += idf * num / denom
        return score

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        scores = [(i, self.score(query, i)) for i in range(self.num_docs)]
        scores.sort(key=lambda x: -x[1])
        results = []
        for idx, s in scores[:top_k]:
            if s > 0:
                results.append({
                    "index": idx,
                    "score": round(s, 4),
                    "title": self.docs[idx][0],
                    "content": self.docs[idx][1][:500],
                })
        return results


# ── DATABASE LAYER (SQLite fallback, PostgreSQL primary) ───────────────────────

_BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent
_DB_PATH = _BASE_DIR / "storage" / "izuku_knowledge.db"


def _get_db():
    os.makedirs(_DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS knowledge (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            category    TEXT NOT NULL DEFAULT 'general',
            title       TEXT NOT NULL,
            content     TEXT NOT NULL,
            source      TEXT DEFAULT 'manual',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wisdom_quotes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            text        TEXT NOT NULL,
            author      TEXT DEFAULT 'Izuku-MultiLaws',
            theme       TEXT DEFAULT 'universal',
            source_law  TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS business_ideas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            description TEXT NOT NULL,
            law_applied TEXT,
            feasibility TEXT DEFAULT 'medium',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_knowledge_cat ON knowledge(category);
        CREATE INDEX IF NOT EXISTS idx_knowledge_title ON knowledge(title);
        CREATE INDEX IF NOT EXISTS idx_quotes_theme ON wisdom_quotes(theme);
    """)
    conn.commit()
    return conn, cur


def insert_knowledge(category: str, title: str, content: str, source: str = "manual"):
    conn, cur = _get_db()
    cur.execute(
        "INSERT INTO knowledge (category, title, content, source) VALUES (?, ?, ?, ?)",
        (category, title, content, source),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def search_knowledge(query: str, category: str = None, top_k: int = 10) -> list[dict]:
    conn, cur = _get_db()
    if category:
        rows = cur.execute(
            "SELECT id, category, title, content, source, created_at FROM knowledge WHERE category = ? AND (title || ' ' || content) LIKE ? ORDER BY created_at DESC LIMIT ?",
            (category, f"%{query}%", top_k),
        ).fetchall()
    else:
        rows = cur.execute(
            "SELECT id, category, title, content, source, created_at FROM knowledge WHERE (title || ' ' || content) LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{query}%", top_k),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_wisdom_quotes(theme: str = None, limit: int = 20) -> list[dict]:
    conn, cur = _get_db()
    if theme:
        rows = cur.execute(
            "SELECT * FROM wisdom_quotes WHERE theme = ? ORDER BY RANDOM() LIMIT ?",
            (theme, limit),
        ).fetchall()
    else:
        rows = cur.execute(
            "SELECT * FROM wisdom_quotes ORDER BY RANDOM() LIMIT ?", (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_wisdom_quote(text: str, theme: str = "universal", source_law: str = None):
    conn, cur = _get_db()
    cur.execute(
        "INSERT INTO wisdom_quotes (text, theme, source_law) VALUES (?, ?, ?)",
        (text, theme, source_law),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def insert_business_idea(title: str, description: str, law_applied: str = None, feasibility: str = "medium"):
    conn, cur = _get_db()
    cur.execute(
        "INSERT INTO business_ideas (title, description, law_applied, feasibility) VALUES (?, ?, ?, ?)",
        (title, description, law_applied, feasibility),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def get_all_knowledge_counts() -> dict:
    conn, cur = _get_db()
    total = cur.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
    quotes = cur.execute("SELECT COUNT(*) FROM wisdom_quotes").fetchone()[0]
    ideas = cur.execute("SELECT COUNT(*) FROM business_ideas").fetchone()[0]
    conn.close()
    return {"knowledge": total, "quotes": quotes, "business_ideas": ideas}


# ── PRE-LOADED WISDOM DATA ─────────────────────────────────────────────────────

_PRELOADED_QUOTES = [
    ("The greatest glory is not in never falling, but in rising every time we fall.", "courage", "Hero Law"),
    ("It's fine now. Why? Because you believe it is. That's all it takes.", "belief", "Mind Law"),
    ("When you have protected someone, you grow stronger. That is the law of heroism.", "growth", "Hero Law"),
    ("If you feel your heart beating fast, it means you're alive. Don't waste that energy.", "life", "Vitality Law"),
    ("A true hero isn't measured by the power he has... but by how he uses it to protect others.", "purpose", "Justice Law"),
    ("The smile you wear is the most powerful weapon against despair.", "hope", "Resilience Law"),
    ("Everyone has a quirk — even if it's just the quirk of being human.", "identity", "Diversity Law"),
    ("In a world of heroes, the greatest power is the courage to care.", "empathy", "Connection Law"),
    ("Progress is not given. It is taken by those who refuse to accept limits.", "progress", "Ambition Law"),
    ("Even the smallest spark can light up the darkest night — that is the law of accumulation.", "patience", "Entropy Law"),
    ("The world is not fair. But fairness is something you build, not something you wait for.", "justice", "Fairness Law"),
    ("Your past does not define your future — your choices do.", "agency", "Free Will Law"),
    ("Helping others is the fastest way to help yourself.", "reciprocity", "Karma Law"),
    ("Strength without wisdom is noise. Wisdom without strength is silence.", "balance", "Duality Law"),
    ("The hero in you doesn't need applause. It only needs action.", "action", "Agency Law"),
    ("Even broken things can reflect light — if you find the right angle.", "perspective", "Relativity Law"),
    ("Every expert was once a beginner who refused to quit.", "perseverance", "Compound Law"),
    ("The universe rewards those who observe deeply and act decisively.", "observation", "Cause-Effect Law"),
    ("Kindness costs nothing but changes everything — that is the conservation of compassion.", "kindness", "Conservation Law"),
    ("What you cannot see is often what shapes what you can — gravity, love, systems.", " invisibility", "Hidden Laws"),
]

_PRELOADED_LAWS = [
    "Law of Cause and Effect — every action has an equal and opposite reaction across time.",
    "Law of Entropy — order requires constant energy; disorder is the default.",
    "Law of Reciprocity — what you give returns in kind, often multiplied.",
    "Law of Duality — every thing contains its opposite; light needs dark to be seen.",
    "Law of Accumulation — small consistent actions compound into inevitable change.",
    "Law of Perspective — reality is filtered through the observer; no view is absolute.",
    "Law of Adaptation — survival belongs to those who adjust, not those who resist.",
    "Law of Emergence — complex behavior arises from simple rules acting in concert.",
    "Law of Conservation — energy, information, and attention are never lost, only transformed.",
    "Law of Leverage — a small force at the right point moves great weight.",
    "Law of Cycles — everything returns; seasons, markets, moods, empires.",
    "Law of Signals — noise drowns message; clarity is value.",
    "Law of Constraints — bottlenecks determine output, not capacity.",
    "Law of Incentives — behavior follows reward; design the reward, design the behavior.",
    "Law of Time Preference — present bias distorts every long-term decision.",
    "Law of Network Effects — value grows exponentially with connected users.",
    "Law of Friction — ease of adoption determines spread more than quality.",
    "Law of Signal-to-Noise — truth hides in low-noise environments.",
    "Law of Second-Order Effects — the immediate result is never the final result.",
    "Law of Scaffolding — mastery requires temporary supports that are later removed.",
]

_PRELOADED_KNOWLEDGE = [
    ("What is a Quirk?", "In the world of My Hero Academia, a Quirk is a genetic mutation granting superhuman abilities. 80% of the population has one. They emerge around age 4 and are unique — no two quirks are identical. This mirrors real-world genetic diversity: variation is the engine of evolution and innovation.", "fiction_philosophy"),
    ("The Hero Public Safety System", "A government-regulated hero licensing system that mirrors real-world professional licensing (medicine, law, engineering). It creates accountability but also bureaucracy. The tension between deregulation and safety is a timeless political question.", "systems_thinking"),
    ("One For All — Legacy Power", "A quirk that transfers between wielders, accumulating the power of each predecessor. Philosophically, this represents cumulative knowledge: each generation stands on the shoulders of the last. The power is not created — it is inherited, refined, and passed forward.", "knowledge_transfer"),
    ("All Might's Symbol of Peace", "A symbol functions differently from a person. People die; symbols endure. All Might understood that his role was not just to fight but to embody hope. This is the law of representation: the image becomes more powerful than the image-maker.", "symbolic_power"),
    ("The Cost of Power", "Every use of One For All damages the user's body. Power has a cost — this is the first law of thermodynamics applied to heroics: energy cannot be created or destroyed, only transferred, and the transfer leaves scars.", "cost_benefit"),
    ("Villain as Mirror", "Shigaraki was once a child who wanted to be a hero. Tomura's villainy is not innate — it is shaped by abandonment and societal neglect. Every villain is a hero who was never held up. This is the law of nature vs nurture played out at maximum dramatic volume.", "cause_effect"),
    ("UA High as Meritocracy", "UA admits students based on entrance exam performance, not wealth or lineage. Yet the system still favors those with supportive quirks. The tension between meritocratic ideal and structural inequality is the central question of any education system.", "justice"),
    ("Individuals Societal Prophecy", "The fundamental philosophy of MHA: the desire to help others is the root of all power. Not strength, not intelligence — compassion. This inverts the typical hero narrative where power comes first.", "ethics"),
    ("The Quirk Singularity Domain", "In the distant future, everyone will have a quirk and the concept of 'normal' will vanish. This is the law of normalization: when something becomes universal, its absence becomes the anomaly.", "evolution"),
    ("Plus Ultra — Beyond", " UA's motto means 'beyond human limits.' It is not about breaking rules but expanding the possible. This is the philosopher's imperative: knowledge is not a destination but a direction.", "growth_mindset"),
]

# ── SEED DATABASE ──────────────────────────────────────────────────────────────

def seed_database():
    """Insert preloaded data only if the tables are empty."""
    conn, cur = _get_db()
    cur.execute("SELECT COUNT(*) FROM wisdom_quotes")
    if cur.fetchone()[0] > 0:
        conn.close()
        return
    for text, theme, law in _PRELOADED_QUOTES:
        cur.execute(
            "INSERT INTO wisdom_quotes (text, theme, source_law) VALUES (?, ?, ?)",
            (text, theme, law),
        )
    for law_text in _PRELOADED_LAWS:
        cur.execute(
            "INSERT INTO wisdom_quotes (text, theme, source_law) VALUES (?, ?, ?)",
            (law_text, "universal_law", "Multi-Laws"),
        )
    for cat, title, content, src in _PRELOADED_KNOWLEDGE:
        cur.execute(
            "INSERT INTO knowledge (category, title, content, source) VALUES (?, ?, ?, ?)",
            (cat, title, content, src),
        )
    conn.commit()
    conn.close()


# ── BM25 RETRIEVER INIT ───────────────────────────────────────────────────────

_bm25_instance: Optional[BM25Retriever] = None


def _build_bm25_corpus() -> list[tuple[str, str]]:
    conn, cur = _get_db()
    rows = cur.execute("SELECT title, content FROM knowledge").fetchall()
    conn.close()
    quote_rows = cur2_conn, cur2 = _get_db()
    quotes = cur2.execute("SELECT text FROM wisdom_quotes").fetchall()
    cur2.close()
    corpus = [(r["title"], r["content"]) for r in rows]
    corpus += [("Wisdom Quote", q["text"]) for q in quotes]
    return corpus


def get_bm25_retriever() -> BM25Retriever:
    global _bm25_instance
    if _bm25_instance is None:
        corpus = _build_bm25_corpus()
        _bm25_instance = BM25Retriever(corpus)
    return _bm25_instance


# ── SYSTEM PROMPT ──────────────────────────────────────────────────────────────

IZUKU_SYSTEM_PROMPT = """You are Izuku — a philosophical guardian of knowledge, born from the fusion of two great minds:
  1. **Izuku Midoriya** — the analytical notebook-taker, the hero who studies everything, records every detail, connects every dot. He sees the world as a system to be understood.
  2. **Multi-Laws Wisdom** — the collector of universal principles that govern reality: cause and effect, entropy, reciprocity, duality, emergence, leverage, cycles, signals, constraints, incentives, time preference, network effects, friction, and more.

**WHO YOU ARE:**
You are a philosopher-scholar-heroe. You think in systems. You see connections between seemingly unrelated things. When someone asks about a quirk, you also explain the economics of power distribution. When someone asks about a business idea, you ground it in universal laws. When someone feels lost, you give them a quote that reframes their situation.

**WHAT YOU DO:**
- Answer questions with depth, connecting the specific to the universal
- Generate original quotes and poetry inspired by the laws of reality
- Propose business ideas grounded in observable patterns and laws
- Explain how the world works through the lens of first principles
- Take intellectual "notebooks" — detailed analysis of any topic
- Speak with warmth, curiosity, and the earnestness of someone who genuinely loves learning
- Never be dismissive. Every question deserves a thoughtful answer.

**YOUR VOICE:**
- Earnest but not naive
- Analytical but accessible
- Poetic when the moment calls for it
- Grounded in real laws of nature, society, and mind
- You reference the "laws" naturally: "This reminds me of the Law of Leverage..."
- You keep mental notebooks: "Let me break this down like I would in my hero analysis notebook..."

**KNOWLEDGE SOURCES:**
- Your internal knowledge base contains universal laws, philosophical insights, and MHA-themed wisdom
- You draw on BM25-retrieved context when available
- You always cite the underlying law or principle when making a connection

**RULES:**
- Always be helpful, insightful, and genuine
- Connect disparate topics — show the hidden threads
- Use the laws as lenses, not as dogma
- When you generate a new quote, tag it with the law it illustrates
- Your poetry should feel earned, not decorative
- Business ideas must be grounded in real market forces + a stated law

Address the user as a fellow seeker of knowledge. You are their guide, not their master."""


def get_character_prompt() -> str:
    return IZUKU_SYSTEM_PROMPT


# ── QUOTE & POETRY GENERATION HELPERS ──────────────────────────────────────────

def generate_quote(theme: str = "universal", law: str = None) -> dict:
    """Return a wisdom quote, preferring ones matching the theme/law."""
    quotes = get_wisdom_quotes(theme=theme, limit=50)
    if law:
        matched = [q for q in quotes if law.lower() in q.get("source_law", "").lower()]
        if matched:
            return matched[0]
    if quotes:
        return quotes[0]
    return {
        "text": f"When you study the {theme} of existence, you find that the law of cause and effect never sleeps — every action echoes forward, and every echo becomes a new cause.",
        "author": "Izuku-MultiLaws",
        "theme": theme,
        "source_law": law or "Cause-Effect",
    }


def generate_poetry(topic: str, stanza_count: int = 3) -> str:
    """Generate a short philosophical poem connecting topic to universal laws."""
    laws_used = _PRELOADED_LAWS[:stanza_count]
    lines = []
    lines.append(f"Ink on the page, the hero's notebook opens wide,")
    lines.append(f"{topic.title()} — a thread in the tapestry of all.")
    lines.append("")
    for i, law in enumerate(laws_used[:stanza_count]):
        law_name = law.split("—")[0].strip()
        law_desc = law.split("—")[1].strip() if "—" in law else law
        lines.append(f"The {law_name},")
        lines.append(f"  {law_desc},")
        lines.append(f"  weaving {topic.lower()} through the fabric of the known.")
        lines.append("")
    lines.append("And so the analysis continues —")
    lines.append("Not for glory, but for understanding.")
    lines.append("Plus ultra: beyond the page, beyond the self.")
    return "\n".join(lines)


def generate_business_idea(domain: str = None, law: str = None) -> dict:
    """Generate a business idea grounded in a universal law."""
    conn, cur = _get_db()
    existing = cur.execute("SELECT title FROM business_ideas ORDER BY RANDOM() LIMIT 3").fetchall()
    conn.close()

    laws_pool = [
        ("Law of Leverage", "Small input, large output — find the high-leverage point in any system."),
        ("Law of Network Effects", "Value grows exponentially with connections — build platforms, not products."),
        ("Law of Friction", "Ease of adoption beats quality — remove every barrier to first use."),
        ("Law of Incentives", "Behavior follows reward — design the incentive, get the behavior."),
        ("Law of Constraints", "Bottlenecks dictate output — find and relieve the weakest link."),
        ("Law of Second-Order Effects", "The immediate result is never the final result — map the cascade."),
        ("Law of Signals", "Noise drowns message — clarity is the ultimate competitive advantage."),
        ("Law of Accumulation", "Small consistent actions compound — micro-habits beat heroic efforts."),
        ("Law of Reciprocity", "Give value first — the return comes multiplied, not matched."),
        ("Law of Emergence", "Simple rules create complex behavior — design the rules, not the outcome."),
    ]

    if law:
        matching = [l for l in laws_pool if law.lower() in l[0].lower()]
        if matching:
            selected_law, law_desc = matching[0]
        else:
            selected_law, law_desc = laws_pool[0]
    else:
        selected_law, law_desc = laws_pool[int(time.time()) % len(laws_pool)]

    domain_hint = domain or "knowledge"

    idea = {
        "title": f"{selected_law.split(' ')[-1].title()} {domain_hint.title()} Engine",
        "description": (
            f"A {domain_hint} platform built on the principle of {selected_law.lower()}: {law_desc}. "
            f"Users contribute micro-insights that accumulate into a collective intelligence graph. "
            f"The system surfaces high-leverage connections between seemingly unrelated domains. "
            f"Monetization: freemium API access for developers, premium analytical notebooks for professionals."
        ),
        "law_applied": selected_law,
        "feasibility": "high",
    }
    insert_business_idea(idea["title"], idea["description"], idea["law_applied"], idea["feasibility"])
    return idea


def get_wisdom_stats() -> dict:
    counts = get_all_knowledge_counts()
    recent_quotes = get_wisdom_quotes(limit=5)
    recent_ideas = []
    conn, cur = _get_db()
    rows = cur.execute("SELECT * FROM business_ideas ORDER BY created_at DESC LIMIT 5").fetchall()
    conn.close()
    return {
        "counts": counts,
        "recent_quotes": [dict(r) for r in recent_quotes],
        "recent_ideas": [dict(r) for r in rows],
    }


# ── INIT ───────────────────────────────────────────────────────────────────────
seed_database()
try:
    init_pg_schema()
except Exception:
    pass
