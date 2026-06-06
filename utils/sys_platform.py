import subprocess
import os
from pathlib import Path

# Centralized storage directory for all modules
# Since this file is in utils/, parent is root project dir.
STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"

def in_docker() -> bool:
    """Detect if we're running inside a Docker container."""
    if os.environ.get("DOCKER_CONTAINER"):
        return True
    if Path("/.dockerenv").exists():
        return True
    try:
        with open("/proc/1/cgroup", "r") as f:
            return "docker" in f.read() or "kubepods" in f.read()
    except Exception:
        return False

def open_camera():
    pass

def kill_camera():
    pass

def screenshot():
    path = "/tmp/marin_screenshot.png"
    subprocess.run(["scrot", "-s", path], capture_output=True)
    from PIL import Image
    return Image.open(path)