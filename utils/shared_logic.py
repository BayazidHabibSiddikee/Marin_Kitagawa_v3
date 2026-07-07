import os
import subprocess
import time
from datetime import datetime
from typing import Any

import database

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
def get_user_context() -> str:
    now = datetime.now()
    time_str = now.strftime("%A, %B %d, %Y | %I:%M %p")
    return f"""
User:
Location: Rajshahi, Bangladesh
Status: Self-directed student
Focus Areas: Embedded systems, IoT, ML, computer vision, robotics, control systems
Active Projects: None currently assigned
Learning Style: Project-driven, hands-on, prefers doing over reading
Personality: High output, ambitious, systematic, appreciates direct communication
Preferences: Concise answers, technical depth when needed, no fluff
Book Library: 60+ technical books on ML, embedded systems, robotics, hacking, Linux, mathematics

[CURRENT SYSTEM TIME]
{time_str}
"""

USER_CONTEXT = get_user_context() # Legacy support, though this will be static
# ── Study Timer ────────────────────────────────────────────────────────────────
class StudyTimer:
    """Track focus sessions and store them in the database."""

    def __init__(self):
        self.current_id: int | None = None
        self.current_task: str | None = None
        self.start_time: float = 0

    def start_session(self, task: str):
        self.current_task = task
        self.start_time = time.time()
        self.current_id = database.start_timer(task)
        print(f"⏱️ Focus session started: {task}")

        # Trigger background book download and indexing for the session topic
        import threading
        threading.Thread(target=self._prepare_session_materials, args=(task,), daemon=True).start()

    def _prepare_session_materials(self, topic: str):
        """Background task: download 3-4 books about the topic and index them."""
        # Use a persistent log for visibility
        log_path = os.path.join(BASE_DIR, "logs", "session_prep.log")
        def _log(msg):
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a") as f:
                f.write(f"[{datetime.now()}] {msg}\n")
            print(msg)

        _log(f"📚 Marin is gathering materials for: {topic}...")
        try:
            from tools.pdf_downloader_marin import marin_search_and_download

            # Directory from user request
            vault_dir = os.path.join(BASE_DIR, "unique", "marin_vault")
            os.makedirs(vault_dir, exist_ok=True)

            queries = [
                f"{topic} technical book",
                f"Advanced {topic} engineering",
                f"{topic} specialized manual"
            ]

            downloaded_count = 0
            for q in queries:
                _log(f"🔍 Searching for: {q}...")
                path = marin_search_and_download(q, download_dir=vault_dir)
                if path:
                    downloaded_count += 1
                    _log(f"✅ Downloaded: {path}")
                if downloaded_count >= 3: break

            if downloaded_count > 0:
                _log(f"🧠 {downloaded_count} materials added to marin_vault. Ready for analysis.")
                # Trigger RAG update if the server is reachable
                try:
                    import requests
                    requests.post("http://localhost:5080/update", json={"path": vault_dir}, timeout=2)
                except Exception: pass
            else:
                _log("⚠️ No specific materials found, but I will use my internal knowledge base.")
        except Exception as e:
            _log(f"❌ Failed to gather materials: {e}")

    def end_session(self, status: str = "completed") -> dict[str, Any] | None:
        if not self.current_id:
            return None

        database.end_timer(self.current_id, status)
        elapsed = time.time() - self.start_time
        task = self.current_task

        self.current_id = None
        self.current_task = None
        self.start_time = 0

        return {"task": task, "elapsed_seconds": int(elapsed), "status": status}

    def get_session_status(self) -> dict[str, Any]:
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

    def get_stats(self) -> dict[str, Any]:
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

async def handle_timer_command(command: str, task: str = "") -> str:
    db = database

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
    if command == "resume":
        last = db.get_last_timer()
        if not last:
            return "No previous session found to resume."
        task = last["task"]
        # If there's an active one already for this task, just say so
        if timer.current_task == task:
            return f"Session for '{task}' is already active."

        timer.start_session(task)
        return (
            f"⚔️ **SESSION RESUMED**\n"
            f"Task: {task}\n"
            f"Time resumed: {datetime.now().strftime('%H:%M')}\n\n"
            f"Picking up where we left off. 🐸"
        )

    if command == "stop":
        session = timer.end_session()
        if not session:
            return "No active session to stop."
        return (
            f"⚔️ **SESSION COMPLETE**\n"
            f"Task: {session['task']}\n"
            f"Duration: {timer._format_duration(session['elapsed_seconds'])}\n"
            f"Great work. Momentum preserved. 🐸"
        )
    if command == "status":
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

