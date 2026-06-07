import os
import subprocess
import shlex
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
            # Use shell=True inside docker to allow pipes/redirection
            # This is safe because the environment itself is isolated
            r = subprocess.run(
                command, shell=True,
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
        # We are on the host, use docker exec for isolation
        try:
            # Check if container is running
            check_running = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", DOCKER_CONTAINER_NAME],
                capture_output=True, text=True
            )
            if "true" not in check_running.stdout:
                # Attempt to start it
                subprocess.run(["docker", "start", DOCKER_CONTAINER_NAME], capture_output=True)
            
            # Use docker exec with bash -c to support pipes/redirection inside the container
            docker_cmd = ["docker", "exec", DOCKER_CONTAINER_NAME, "bash", "-c", command]
            
            r = subprocess.run(
                docker_cmd, shell=False,
                capture_output=True, text=True, timeout=timeout + 5
            )
            return r.returncode, (r.stdout + r.stderr).strip()
        except subprocess.TimeoutExpired:
            return -1, f"Docker command timed out after {timeout}s"
        except Exception as e:
            return -1, f"Host execution error: {e}. Ensure Docker is running."

if __name__ == "__main__":
    code, out = run_command("whoami && pwd")
    print(f"Code: {code}\nOutput: {out}")
