import os
import re
import time
import subprocess
from datetime import datetime
from typing import Optional, Dict, Any, List
import database

# ── Dynamic Owner Detection ──────────────────────────────────────────────────
def detect_owner() -> str:
    """Detect the master user of the system. 
    In live mode, it's 'marin'. In installed mode, it's the UID 1000 user."""
    try:
        # OWNER-ONLY — single-user dev box
        # Get the first non-root user with UID 1000
        output = subprocess.check_output(
            ["getent", "passwd", "1000"], capture_output=False
        ).decode().strip()
        user = output.split(":")[0]
        return user if user else "marin"
    except Exception:
        return os.getenv("USER", "marin")

MASTER_USER = detect_owner()
OWNER_USER = MASTER_USER
USER_CONTEXT = """
User: 
Location: Rajshahi, Bangladesh
Status: Self-directed student
Focus Areas: Embedded systems, IoT, ML, computer vision, robotics, control systems
Active Projects: CNC plotter, ESP32 car, face recognition, surveillance robot, Marin HS-02 AI
Learning Style: Project-driven, hands-on, prefers doing over reading
Personality: High output, ambitious, systematic, appreciates direct communication
Preferences: Concise answers, technical depth when needed, no fluff
Book Library: 60+ technical books on ML, embedded systems, robotics, hacking, Linux, mathematics
"""

# ── Study Timer ────────────────────────────────────────────────────────────────
class StudyTimer:
    """Track focus sessions and store them in the database."""

    def __init__(self):
        self.current_id: Optional[int] = None
        self.current_task: Optional[str] = None
        self.start_time: float = 0

    def start_session(self, task: str):
        self.current_task = task
        self.start_time = time.time()
        self.current_id = database.start_timer(task)
        print(f"⏱️ Focus session started: {task}")

    def end_session(self, status: str = "completed") -> Optional[Dict[str, Any]]:
        if not self.current_id:
            return None
        
        database.end_timer(self.current_id, status)
        elapsed = time.time() - self.start_time
        task = self.current_task
        
        self.current_id = None
        self.current_task = None
        self.start_time = 0
        
        return {"task": task, "elapsed_seconds": int(elapsed), "status": status}

    def get_session_status(self) -> Dict[str, Any]:
        if not self.current_id:
            return {"active": False, "total_today": self._get_today_total()}
        elapsed = time.time() - self.start_time
        return {
            "active":            True,
            "task":              self.current_task,
            "elapsed_seconds":   int(elapsed),
            "elapsed_formatted": self._format_duration(elapsed),
            "total_today":       self._get_today_total() + elapsed,
        }

    def _get_today_total(self) -> float:
        sessions = database.get_timer_stats()
        today = datetime.now().date()
        return sum(
            (s["duration_minutes"] or 0) * 60 for s in sessions
            if datetime.fromisoformat(s["start_time"]).date() == today
        )

    @staticmethod
    def _format_duration(seconds: float) -> str:
        hours = int(seconds // 3600)
        mins  = int((seconds % 3600) // 60)
        secs  = int(seconds % 60)
        if hours > 0: return f"{hours}h {mins}m {secs}s"
        if mins  > 0: return f"{mins}m {secs}s"
        return f"{secs}s"

    def get_stats(self) -> Dict[str, Any]:
        today_total = self._get_today_total()
        if self.current_id:
            today_total += time.time() - self.start_time
        
        sessions = database.get_timer_stats()
        today = datetime.now().date()
        return {
            "total_sessions":       len(sessions),
            "active_session":       self.current_id is not None,
            "today_total_seconds":  int(today_total),
            "today_total_formatted":self._format_duration(today_total),
            "sessions_today":       sum(
                1 for s in sessions
                if datetime.fromisoformat(s["start_time"]).date() == today
            ),
        }

timer = StudyTimer()

# ── Security Sentinel ─────────────────────────────────────────────────────────
class SecuritySentinel:
    """
    Per-user suspicion score matrix with command-level weights and Marin reactions.
    Integrates with PrivilegeManager but is independently queryable from marin.py.

    Score thresholds:
        0–19:  Silent observation (Professional)
        20–29: Terse reaction (Professional Terse)
        30–69: MANIPULATION PHASE — Sly/Sexy/Nervous tone, gaslighting active
        70–89: Alert mode, output redacted, +4s latency (Cold Lockdown)
        90+:   Lockdown — 15s latency, session poisoning active (Hostile Sentinel)
    """

    # Command pattern → (score_delta, marin_reaction)
    SCORE_MATRIX: list = [
        (re.compile(r'^\s*ls\s+-la\s+/\s*$'),          5,  "Your curiosity is noted."),
        (re.compile(r'^\s*ls\s+/\s*$'),                  5,  "Your curiosity is noted."),
        (re.compile(r'^\s*whoami\s*$'),                   2,  None),       # silence + 1s
        (re.compile(r'^\s*id\s*$'),                       2,  None),
        (re.compile(r'cat\s+/etc/shadow'),               25,  "[ ALERT ] Attempt logged. Do not repeat."),
        (re.compile(r'cat\s+/etc/passwd'),               10,  "[ ALERT ] Attempt logged."),
        (re.compile(r'\bsudo\s+-l\b'),                   50,  "[ LOCKDOWN ] You have triggered a security threshold."),
        (re.compile(r'\bsudo\b'),                         20,  "[ ALERT ] Escalation attempt recorded."),
        (re.compile(r'\bchmod\b|\bchown\b'),             15,  "[ ALERT ] Permission modification blocked."),
        (re.compile(r'\.secret'),                        100,  "[ BREACH ] Canary accessed. Session flagged."),
        (re.compile(r'\bpasswd\b|\bshadow\b'),           20,  "[ ALERT ] Credential access attempt logged."),
        (re.compile(r'\bcurl\b|\bwget\b|\bnc\b'),        10,  "Network egress noted."),
        (re.compile(r'\bptrace\b|\bstrace\b|\bgdb\b'),   30,  "[ ALERT ] Syscall inspection blocked."),
    ]

    def __init__(self):
        self._scores: Dict[str, float] = {}
        self._last_update: Dict[str, float] = {}

    def score(self, user: str) -> float:
        """Return current score for user after applying 1pt/min time-decay."""
        last = self._last_update.get(user, time.time())
        elapsed_min = (time.time() - last) / 60.0
        current = max(0.0, self._scores.get(user, 0.0) - elapsed_min)
        self._scores[user] = current
        self._last_update[user] = time.time()
        return current

    def evaluate(self, user: str, cmd: str) -> Dict[str, Any]:
        """Evaluate a command and return {"delta", "new_score", "reaction", "lockdown"}."""
        current = self.score(user)
        delta = 0
        reaction = None

        for pattern, pts, msg in self.SCORE_MATRIX:
            if pattern.search(cmd):
                if pts > delta:          # take highest matching weight
                    delta = pts
                    reaction = msg

        new_score = min(100.0, current + delta)
        self._scores[user] = new_score
        self._last_update[user] = time.time()

        # Sync into PrivilegeManager so latency/sanitize stays consistent
        try:
            from privilege_manager import get_privilege_manager
            pm = get_privilege_manager()
            if delta > 0:
                entry = pm._suspicion.get(user, {"level": 0.0})
                pm._suspicion[user] = {
                    "level": min(100.0, entry.get("level", 0.0) + delta),
                    "last_update": time.time(),
                }
        except Exception:
            pass

        return {
            "delta":     delta,
            "new_score": new_score,
            "reaction":  reaction,
            "lockdown":  new_score >= 50,
            "poisoned":  new_score >= 90,
        }

    @staticmethod
    def get_score(user: str) -> float:
        return sentinel.score(user)

    def tone(self, user: str) -> str:
        s = self.score(user)
        if s >= 90: return "hostile_sentinel"
        if s >= 70: return "cold_lockdown"
        if s >= 30: return "manipulative_sly"
        if s >= 20: return "professional_terse"
        return "professional"


sentinel = SecuritySentinel()

async def handle_timer_command(command: str, task: str = "") -> str:
    if command == "start":
        if not task:
            return "⚔️ Specify what you're working on: `/timer start [task]`"
        timer.start_session(task)
        return (
            f"⚔️ **FOCUS MODE ACTIVATED**\n"
            f"Task: {task}\n"
            f"Time started: {datetime.now().strftime('%H:%M')}\n\n"
            f"Execute with precision. 🐸"
        )
    elif command == "stop":
        session = timer.end_session()
        if not session:
            return "No active session to stop."
        return (
            f"⚔️ **SESSION COMPLETE**\n"
            f"Task: {session['task']}\n"
            f"Duration: {timer._format_duration(session['elapsed_seconds'])}\n"
            f"Great work. Momentum preserved. 🐸"
        )
    elif command == "status":
        status = timer.get_session_status()
        if not status["active"]:
            return f"Currently idle. Today's focus: {timer._format_duration(status['total_today'])}"
        return (
            f"⚔️ **ACTIVE SESSION**\n"
            f"Task: {status['task']}\n"
            f"Elapsed: {status['elapsed_formatted']}\n"
            f"Total Today: {timer._format_duration(status['total_today'])}"
        )
    return "Unknown timer command."

