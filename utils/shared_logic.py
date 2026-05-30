import os
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
import database

# ── User Context ──────────────────────────────────────────────────────────────
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

