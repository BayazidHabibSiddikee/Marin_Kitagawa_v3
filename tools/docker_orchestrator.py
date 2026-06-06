import docker
import time
from typing import List, Dict, Any, Optional

class DockerOrchestrator:
    def __init__(self):
        self.client = None
        self._connect()

    def _connect(self):
        """Attempt to connect to the Docker daemon with a retry mechanism."""
        try:
            self.client = docker.from_env()
            self.client.ping() # Verify connection
        except Exception as e:
            self.client = None
            print(f"[DockerOrchestrator] Connection failed: {e}")

    def _check_client(self):
        if not self.client:
            self._connect() # Try once more
            if not self.client:
                raise RuntimeError("Docker daemon is inaccessible. Ensure /var/run/docker.sock is mounted.")

    def list_containers(self, all: bool = False) -> List[Dict[str, Any]]:
        self._check_client()
        containers = self.client.containers.list(all=all)
        return [
            {
                "id": c.short_id,
                "name": c.name,
                "status": c.status,
                "image": c.image.tags[0] if c.image.tags else c.image.id
            } for c in containers
        ]

    def create_container(self, image: str, name: str, **kwargs) -> str:
        """Spin up a new container in the kingdom."""
        self._check_client()
        try:
            container = self.client.containers.run(
                image, name=name, detach=True, **kwargs
            )
            return f"Successfully created and started container: {name} (ID: {container.short_id})"
        except Exception as e:
            return f"Failed to create container {name}: {e}"

    def remove_container(self, name: str, force: bool = False) -> str:
        """Remove a container from the kingdom."""
        self._check_client()
        try:
            container = self.client.containers.get(name)
            container.remove(force=force)
            return f"Container {name} removed."
        except Exception as e:
            return f"Failed to remove container {name}: {e}"

    def exec_run(self, name: str, command: str) -> str:
        """Execute a command inside a running container."""
        self._check_client()
        try:
            container = self.client.containers.get(name)
            exit_code, output = container.exec_run(command)
            return f"Exit Code: {exit_code}\nOutput:\n{output.decode('utf-8')}"
        except Exception as e:
            return f"Execution error in {name}: {e}"

    def start_container(self, name: str) -> str:
        self._check_client()
        try:
            container = self.client.containers.get(name)
            container.start()
            return f"Container {name} started successfully."
        except Exception as e:
            return f"Failed to start container {name}: {e}"

    def stop_container(self, name: str) -> str:
        self._check_client()
        try:
            container = self.client.containers.get(name)
            container.stop()
            return f"Container {name} stopped successfully."
        except Exception as e:
            return f"Failed to stop container {name}: {e}"

    def get_stats(self, name: str) -> str:
        self._check_client()
        try:
            container = self.client.containers.get(name)
            stats = container.stats(stream=False)
            
            # CPU
            cpu_stats = stats.get('cpu_stats', {})
            precpu_stats = stats.get('precpu_stats', {})
            cpu_usage = cpu_stats.get('cpu_usage', {}).get('total_usage', 0)
            precpu_usage = precpu_stats.get('cpu_usage', {}).get('total_usage', 0)
            system_cpu_usage = cpu_stats.get('system_cpu_usage', 0)
            system_precpu_usage = precpu_stats.get('system_cpu_usage', 0)
            
            cpu_percent = 0.0
            if system_cpu_usage - system_precpu_usage > 0:
                cpu_delta = cpu_usage - precpu_usage
                system_delta = system_cpu_usage - system_precpu_usage
                num_cpus = cpu_stats.get('online_cpus', len(cpu_stats.get('cpu_usage', {}).get('percpu_usage', [])) or 1)
                cpu_percent = (cpu_delta / system_delta) * num_cpus * 100.0

            # Memory
            mem_usage = stats.get('memory_stats', {}).get('usage', 0)
            mem_limit = stats.get('memory_stats', {}).get('limit', 1)
            mem_percent = (mem_usage / mem_limit) * 100.0
            
            return f"Stats for {name}:\nCPU: {cpu_percent:.2f}%\nMemory: {mem_usage / (1024*1024):.2f}MB / {mem_limit / (1024*1024):.2f}MB ({mem_percent:.2f}%)"
        except Exception as e:
            return f"Failed to get stats for {name}: {e}"

    def restart_container(self, name: str) -> str:
        self._check_client()
        try:
            container = self.client.containers.get(name)
            container.restart()
            return f"Container {name} restarted."
        except Exception as e:
            return f"Failed to restart {name}: {e}"

    def pull_image(self, image: str) -> str:
        self._check_client()
        try:
            self.client.images.pull(image)
            return f"Image {image} pulled successfully."
        except Exception as e:
            return f"Failed to pull image {image}: {e}"

    def compose_action(self, action: str, project_dir: str = ".") -> str:
        """Run basic docker-compose commands via shell (SDK doesn't have native compose)."""
        import subprocess
        try:
            # We use subprocess here because Docker SDK doesn't natively handle compose files well
            cmd = ["docker", "compose", "-f", f"{project_dir}/docker-compose.yml", action, "-d"]
            if action in ("down", "stop"): cmd.pop() # Remove -d
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return f"Compose {action} output:\n{result.stdout}\n{result.stderr}"
        except Exception as e:
            return f"Compose error: {e}"

    def get_logs(self, name: str, tail: int = 50) -> str:
        self._check_client()
        try:
            container = self.client.containers.get(name)
            logs = container.logs(tail=tail).decode('utf-8')
            return f"Logs for {name}:\n{logs}"
        except Exception as e:
            return f"Failed to get logs for {name}: {e}"

# Expose a global instance
orchestrator = DockerOrchestrator()
