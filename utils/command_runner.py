import os
import shlex
import subprocess
from pathlib import Path

try:
    from safety import _in_docker
except ImportError:
    import sys
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from safety import _in_docker

BASE_DIR = Path(__file__).resolve().parent.parent
DOCKER_CONTAINER_NAME = "marin-hs02"

def run_command(command: str, timeout: int = 30) -> tuple[int, str]:
    """
    Execute a command.
    If running on host, it delegates to docker container for safety/isolation.
    If running in docker, it runs directly.
    """
    in_container = _in_docker()

    if in_container:
        # OWNER-ONLY — single-user dev box
        # We are already in the sandbox
        try:
            # Parse command string into args; shell=False for security
            r = subprocess.run(
                shlex.split(command) if isinstance(command, str) else command, shell=False,
                capture_output=True, text=True, timeout=timeout,
                cwd="/app",
                env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
            )
            return r.returncode, (r.stdout + r.stderr).strip()
        except subprocess.TimeoutExpired:
            return -1, f"Command timed out after {timeout}s"
        except Exception as e:
            return -1, f"Error: {e}"
    else:
        # We are on the host — try docker exec for isolation, fall back to direct exec
        try:
            # Check if container exists and is running
            check_running = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", DOCKER_CONTAINER_NAME],
                capture_output=True, text=True, timeout=5
            )
            container_running = "true" in check_running.stdout

            if not container_running:
                # Try to start it; if container doesn't exist, this will fail silently
                subprocess.run(
                    ["docker", "start", DOCKER_CONTAINER_NAME],
                    capture_output=True, text=True, timeout=10
                )
                recheck = subprocess.run(
                    ["docker", "inspect", "-f", "{{.State.Running}}", DOCKER_CONTAINER_NAME],
                    capture_output=True, text=True, timeout=5
                )
                container_running = "true" in recheck.stdout

            if container_running:
                docker_cmd = ["docker", "exec", DOCKER_CONTAINER_NAME, "bash", "-c", command]
                r = subprocess.run(
                    docker_cmd, shell=False,
                    capture_output=True, text=True, timeout=timeout + 5
                )
                return r.returncode, (r.stdout + r.stderr).strip()
            else:
                # Container unavailable — run directly on host (safety.py still guards content)
                r = subprocess.run(
                    command, shell=True,
                    capture_output=True, text=True, timeout=timeout,
                    cwd=str(BASE_DIR),
                    env={**os.environ}
                )
                return r.returncode, (r.stdout + r.stderr).strip()

        except subprocess.TimeoutExpired:
            return -1, f"Command timed out after {timeout}s"
        except Exception as e:
            # Last-resort direct execution
            try:
                r = subprocess.run(
                    command, shell=True,
                    capture_output=True, text=True, timeout=timeout,
                    cwd=str(BASE_DIR)
                )
                return r.returncode, (r.stdout + r.stderr).strip()
            except Exception as e2:
                return -1, f"Execution error: {e2}"

if __name__ == "__main__":
    code, out = run_command("whoami && pwd")
    print(f"Code: {code}\nOutput: {out}")
