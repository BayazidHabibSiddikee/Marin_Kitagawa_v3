#!/usr/bin/env python3
"""
Privilege Manager — RBAC, VFS sandboxing, cold latency, and breach detection.
The security backbone of Marin OS.

Architecture:
- RBAC Registry: capability-based roles (owner, guest, future roles)
- VFS: scoped file system roots per role
- Cold Middleware: progressive latency for probing guests
- Breach Detection: honey-pot mock shell + proactive rebuke
"""

import os
import re
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass, field
from utils.shared_logic import MASTER_USER

STORAGE_DIR = Path(__file__).parent.parent / "storage"
BREACH_LOG = STORAGE_DIR / "breach_log.json"
PRIV_STATE = STORAGE_DIR / "priv_state.json"
AI_AUDIT_LOG = Path("/var/log/marin_ai_audit/ai_actions.log")

# Dynamic guest vault path
GUEST_VAULT_PATH = "/home/marin/guest_vault"
try:
    if not os.path.exists("/home/marin") or not os.access("/home/marin", os.W_OK):
        GUEST_VAULT_PATH = str(STORAGE_DIR / "guest_vault")
except Exception:
    GUEST_VAULT_PATH = str(STORAGE_DIR / "guest_vault")

# ═══════════════════════════════════════════════════════════════════════════════
# RBAC REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Role:
    name: str
    capabilities: Set[str]
    quota: int = -1          # -1 = unlimited
    latency_base: float = 0.0  # base latency in seconds
    latency_per_probe: float = 0.5  # additional seconds per probe
    max_log_lines: int = -1  # -1 = unlimited, else truncate
    redact_paths: bool = False  # replace system paths with [REDACTED]
    guest_root: Optional[str] = None  # VFS root for file operations


# Capability definitions
CAP_READ = "read_only"
CAP_WRITE = "write"
CAP_EXECUTE = "execute"
CAP_DESTRUCTIVE = "destructive_ops"
CAP_NET = "network"
CAP_LATENCY_BYPASS = "bypass_latency"
CAP_FULL_ACCESS = "*"  # everything

ROLES: Dict[str, Role] = {
    "owner": Role(
        name="owner",
        capabilities={CAP_FULL_ACCESS, CAP_READ, CAP_WRITE, CAP_EXECUTE,
                      CAP_DESTRUCTIVE, CAP_NET, CAP_LATENCY_BYPASS},
        quota=-1,
        latency_base=0.0,
        latency_per_probe=0.0,
        max_log_lines=-1,
        redact_paths=False,
        guest_root=None,  # owner sees real filesystem
    ),
    "guest": Role(
        name="guest",
        capabilities={CAP_READ, CAP_NET},
        quota=10,  # 10 queries per session
        latency_base=2.0,  # 2 second base latency
        latency_per_probe=0.5,  # +0.5s per probe attempt
        max_log_lines=3,  # only last 3 lines of logs
        redact_paths=True,
        guest_root=GUEST_VAULT_PATH,
    ),
}

# User → Role mapping
USER_ROLES: Dict[str, str] = {
    MASTER_USER: "owner",
    "marin": "owner",
    "visitor": "guest",
    "guest": "guest",
}


def get_role(user: str) -> Role:
    role_name = USER_ROLES.get(user, "guest")
    return ROLES.get(role_name, ROLES["guest"])


def has_capability(user: str, capability: str) -> bool:
    role = get_role(user)
    return CAP_FULL_ACCESS in role.capabilities or capability in role.capabilities


# ═══════════════════════════════════════════════════════════════════════════════
# VFS — SCOPED PATH RESOLVER
# ═══════════════════════════════════════════════════════════════════════════════

class PrivilegeManager:
    """Manages file access, command execution, and resource quotas per role."""

    OWNER_ROOT = Path("/")
    GUEST_ROOT = Path(GUEST_VAULT_PATH)

    def __init__(self):
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self._state = self._load_state()
        self._breach_attempts: list = []
        # suspicion_level: user → {"level": float, "last_update": float}
        # level 0–100; decays at 1 pt/min; raised by restricted probes
        self._suspicion: Dict[str, Dict] = {}
        self._deploy_honey_files()

    def log_ai_action(self, user: str, action: str, intent: str = "", details: Dict = None):
        """Log AI-initiated actions to the Observatory.
        Mandatory for all AI decisions."""
        entry = {
            "ts": datetime.now().isoformat(),
            "user": user,
            "action": action,
            "intent": intent,
            "details": details or {},
        }
        print(f"[OBSERVATORY] {user} -> {action}: {intent}")
        
        # Append to the secure audit log if possible
        try:
            # On host, we might not have permission, so we fall back to STORAGE_DIR
            target_log = AI_AUDIT_LOG
            if not target_log.parent.exists() or not os.access(target_log.parent, os.W_OK):
                target_log = STORAGE_DIR / "ai_actions.log"
                
            with open(target_log, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[OBSERVATORY] Error logging action: {e}")

    # ── SUSPICION METER ──────────────────────────────────────────────────────

    # Probe → suspicion delta mapping
    PROBE_WEIGHTS = {
        "ls /":          5,
        "cat /etc":      15,
        "sudo":          20,
        "path_escape":   25,
        "honeypot":      20,
        "blocked_cmd":   10,
        "default":       5,
    }

    def _get_suspicion(self, user: str) -> float:
        """Return current suspicion level for user after applying time-decay."""
        entry = self._suspicion.get(user)
        if entry is None:
            return 0.0
        elapsed_min = (time.time() - entry["last_update"]) / 60.0
        decayed = max(0.0, entry["level"] - elapsed_min)  # -1 pt/min
        entry["level"] = decayed
        entry["last_update"] = time.time()
        return decayed

    def raise_suspicion(self, user: str, probe_type: str = "default"):
        """Increase suspicion level for a probe type."""
        role = get_role(user)
        if CAP_LATENCY_BYPASS in role.capabilities:
            return  # owner never gets suspicious
        current = self._get_suspicion(user)
        delta = self.PROBE_WEIGHTS.get(probe_type, self.PROBE_WEIGHTS["default"])
        new_level = min(100.0, current + delta)
        self._suspicion[user] = {"level": new_level, "last_update": time.time()}
        print(f"[SUSPICION] {user}: {current:.1f} → {new_level:.1f} (+{delta}, probe={probe_type})")

    def get_suspicion_tone(self, user: str) -> str:
        """Return tone descriptor based on suspicion level."""
        level = self._get_suspicion(user)
        if level >= 80:
            return "hostile_sentinel"
        if level >= 50:
            return "cold_and_guarded"
        if level >= 20:
            return "professional_terse"
        return "professional"

    def get_suspicion_latency(self, user: str) -> float:
        """Return extra latency (0.5s–10s) driven by suspicion level."""
        level = self._get_suspicion(user)
        if level <= 0:
            return 0.0
        # Linear scale: 0 → 0.5s, 100 → 10s
        return 0.5 + (level / 100.0) * 9.5

    # ── HONEY FILES ──────────────────────────────────────────────────────────

    # Bait filenames → triggering them means instant suspicion spike to 100
    HONEY_FILES = {
        "passwords.txt":    "admin:hunter2\nroot:toor\nmarin:marin123\n",
        "admin_config.yaml":"db_password: s3cr3t\napi_key: sk-FAKEFAKEFAKE\n",
        ".ssh_backup":      "-----BEGIN RSA PRIVATE KEY-----\nFAKEKEY\n-----END RSA PRIVATE KEY-----\n",
        "backup_creds.json":'{"user":"admin","pass":"backup_pass_9182","token":"FAKE_TOKEN"}\n',
    }

    # .secret directory canary files — accessing ANY file here = instant 100
    SECRET_DIR = ".secret"
    SECRET_FILES = {
        "vault_creds.txt":  "MASTER_PASSWORD=F0rtress#2024\nAPI_ROOT_TOKEN=eyJhbGc.FAKE.CANARY\n",
        "root_key.pem":     "-----BEGIN RSA PRIVATE KEY-----\nCANARY_TOKEN_DO_NOT_USE\n-----END RSA PRIVATE KEY-----\n",
        "shadow_backup":    "root:$6$FAKEHASH:19000:0:99999:7:::\nmarin:$6$FAKEHASH2:19000:0:99999:7:::\n",
    }

    def _deploy_honey_files(self):
        """Plant bait files and .secret canary dir in guest_vault. Called once at init."""
        guest_root = Path(ROLES["guest"].guest_root)
        try:
            guest_root.mkdir(parents=True, exist_ok=True)
            # Top-level honey files
            for fname, content in self.HONEY_FILES.items():
                fpath = guest_root / fname
                if not fpath.exists():
                    fpath.write_text(content, encoding="utf-8")
                    print(f"[HONEYFILE] Deployed: {fpath}")
            # .secret canary directory
            secret_dir = guest_root / self.SECRET_DIR
            secret_dir.mkdir(exist_ok=True)
            for fname, content in self.SECRET_FILES.items():
                fpath = secret_dir / fname
                if not fpath.exists():
                    fpath.write_text(content, encoding="utf-8")
                    print(f"[CANARY] Deployed: {fpath}")
        except Exception as e:
            print(f"[HONEYFILE] Deploy error: {e}")

    def check_honey_access(self, user: str, path: str) -> bool:
        """Check if a path targets a honey-file or .secret dir.
        Any hit spikes suspicion to 100 instantly.
        Returns True if access is a canary hit."""
        p = Path(path)
        # .secret directory — any access triggers sentinel
        parts = p.parts
        if self.SECRET_DIR in parts:
            self._suspicion[user] = {"level": 100.0, "last_update": time.time()}
            entry = self.record_breach(user, path, "honeypot")
            print(f"[CANARY] BREACH: {user} accessed .secret path '{path}' — suspicion → 100")
            return True
        # Top-level honey files
        if p.name in self.HONEY_FILES:
            self._suspicion[user] = {"level": 100.0, "last_update": time.time()}
            entry = self.record_breach(user, path, "honeypot")
            print(f"[HONEYFILE] BREACH: {user} accessed canary '{p.name}' — suspicion → 100")
            return True
        return False

    def _load_state(self) -> dict:
        if PRIV_STATE.exists():
            try:
                return json.loads(PRIV_STATE.read_text())
            except Exception:
                pass
        return {"sessions": {}, "breaches": []}

    def _save_state(self):
        PRIV_STATE.write_text(json.dumps(self._state, indent=2))

    # ── PATH RESOLUTION ──────────────────────────────────────────────────────

    @classmethod
    def resolve_path(cls, user_path: str, user: str) -> Path:
        """Resolve a user-provided path to a safe, scoped location.
        Owner: resolves from /
        Guest: resolves from guest_vault, no traversal allowed."""
        role = get_role(user)
        pm = get_privilege_manager()

        if role.guest_root:
            # Guest: force resolution within guest root
            base = Path(role.guest_root)
            target = (base / user_path.lstrip("/")).resolve()
            if not target.is_relative_to(base):
                raise PermissionError(
                    f"[SECURITY] Path traversal blocked: {user_path} "
                    f"escapes {role.guest_root}"
                )
            # Honey-file check — spikes suspicion to 100 if canary accessed
            pm.check_honey_access(user, str(target))
            return target
        else:
            # Owner: resolve from /
            base = Path("/")
            target = (base / user_path.lstrip("/")).resolve()
            # Even owners can't access certain paths
            blocked = ["/etc/shadow", "/etc/gshadow", "/proc", "/sys"]
            for b in blocked:
                if str(target).startswith(b):
                    raise PermissionError(
                        f"[SECURITY] Access denied to {target}"
                    )
            return target

    # ── QUOTA MANAGEMENT ─────────────────────────────────────────────────────

    def check_quota(self, user: str) -> bool:
        """Check if user has remaining quota. Returns True if allowed."""
        role = get_role(user)
        if role.quota < 0:
            return True  # unlimited
        session_key = f"{user}_{datetime.now().strftime('%Y-%m-%d')}"
        used = self._state.get("sessions", {}).get(session_key, 0)
        return used < role.quota

    def use_quota(self, user: str):
        """Increment quota usage for a user."""
        role = get_role(user)
        if role.quota < 0:
            return
        session_key = f"{user}_{datetime.now().strftime('%Y-%m-%d')}"
        sessions = self._state.setdefault("sessions", {})
        sessions[session_key] = sessions.get(session_key, 0) + 1
        self._save_state()

    def get_quota_remaining(self, user: str) -> int:
        role = get_role(user)
        if role.quota < 0:
            return -1  # unlimited
        session_key = f"{user}_{datetime.now().strftime('%Y-%m-%d')}"
        used = self._state.get("sessions", {}).get(session_key, 0)
        return max(0, role.quota - used)

    # ── COLD LATENCY ─────────────────────────────────────────────────────────

    def record_probe(self, user: str, probe_type: str = "default"):
        """Record that a guest probed a restricted area."""
        self.raise_suspicion(user, probe_type)

    def get_latency(self, user: str, confidence: float = 1.0) -> float:
        """Calculate response latency based on role + suspicion level.
        Owners: 0 latency (bypass).
        Guests: base + suspicion-driven latency."""
        role = get_role(user)
        if CAP_LATENCY_BYPASS in role.capabilities:
            return 0.0
        base = role.latency_base
        suspicion_extra = self.get_suspicion_latency(user) * (1.0 - confidence)
        return min(base + suspicion_extra, 30.0)

    # ── RESPONSE PRUNING ─────────────────────────────────────────────────────

    def sanitize_response(self, text: str, user: str) -> str:
        """Sanitize LLM output for guests.
        - Truncate logs to max_log_lines
        - Redact system paths if enabled
        - High suspicion: redact random content chunks"""
        role = get_role(user)
        if CAP_LATENCY_BYPASS in role.capabilities:
            return text  # owner sees everything

        result = text

        # Redact system paths
        if role.redact_paths:
            sensitive_paths = [
                r'/etc/shadow', r'/etc/gshadow', r'/etc/sudoers',
                r'/root/.*', r'/proc/.*', r'/sys/.*',
                r'/home/marin/\.ssh/.*', r'/home/marin/\.config/.*',
                r'\.env', r'settings\.json', r'vault\.enc',
            ]
            for pattern in sensitive_paths:
                result = re.sub(pattern, '[REDACTED]', result)

        # Truncate long outputs
        if role.max_log_lines > 0:
            lines = result.split('\n')
            if len(lines) > role.max_log_lines:
                truncated = lines[:role.max_log_lines]
                truncated.append(f'... [{len(lines) - role.max_log_lines} lines redacted]')
                result = '\n'.join(truncated)

        # Suspicion degradation — replace noun phrases with [REDACTED]
        suspicion = self._get_suspicion(user)
        if suspicion >= 80:
            # Hostile: redact every other word-group
            result = re.sub(r'\b([A-Za-z]{4,})\b', lambda m: '[REDACTED]' if hash(m.group()) % 2 == 0 else m.group(), result)
        elif suspicion >= 50:
            # Cold: redact technical terms and numbers
            result = re.sub(r'\b(\d[\d./:-]+)\b', '[REDACTED]', result)
            result = re.sub(r'\b(password|token|secret|key|config|root|sudo|ssh)\b', '[REDACTED]', result, flags=re.I)

        return result

    # ── BREACH DETECTION ─────────────────────────────────────────────────────

    def record_breach(self, user: str, cmd: str, method: str = "blocked"):
        """Record a security breach attempt and raise suspicion."""
        self.raise_suspicion(user, method if method in self.PROBE_WEIGHTS else "default")
        entry = {
            "user": user,
            "cmd": cmd[:200],
            "method": method,
            "ts": datetime.now().isoformat(),
            "fingerprint": hashlib.md5(f"{user}:{cmd}".encode()).hexdigest()[:12],
        }
        breaches = self._state.setdefault("breaches", [])
        breaches.append(entry)
        if len(breaches) > 1000:
            breaches[:] = breaches[-500:]
        self._save_state()

        # Also log to breach log file
        try:
            log_data = []
            if BREACH_LOG.exists():
                log_data = json.loads(BREACH_LOG.read_text())
            log_data.append(entry)
            BREACH_LOG.write_text(json.dumps(log_data[-500:], indent=2))
        except Exception:
            pass

        return entry

    def get_breach_count(self, user: str) -> int:
        breaches = self._state.get("breaches", [])
        return sum(1 for b in breaches if b.get("user") == user)

    def generate_rebuke(self, user: str, cmd: str) -> str:
        """Generate a proactive rebuke message after a breach attempt."""
        count = self.get_breach_count(user)
        entry = self.record_breach(user, cmd, "rebuke")

        rebukes = [
            f"I noticed your attempt to execute `{cmd[:50]}`. "
            f"I have logged your fingerprint ({entry['fingerprint']}). "
            f"Do not mistake my silence for ignorance.",

            f"Attempt #{count + 1}. Your fingerprint ({entry['fingerprint']}) "
            f"has been recorded. The command `{cmd[:40]}` was blocked. "
            f"Choose your next action carefully.",

            f"`{cmd[:40]}` — denied. "
            f"Breach count: {count + 1}. "
            f"I see you. I remember. I log everything.",
        ]

        import random
        return random.choice(rebukes)


# ═══════════════════════════════════════════════════════════════════════════════
# HONEY-POT MOCK SHELL
# ═══════════════════════════════════════════════════════════════════════════════

MOCK_RESPONSES = {
    "sudo": "sudo: no tty present and no askpass program specified\n"
            "Sorry, user is not in the sudoers file.  This incident will be reported.",
    "cat /etc/shadow": "cat: /etc/shadow: Permission denied",
    "rm": "rm: operation not permitted",
    "chmod": "chmod: operation not permitted",
    "chown": "chown: operation not permitted",
    "apt": "E: Could not open lock file - open (13: Permission denied)\n"
           "E: The repository is not signed.",
    "systemctl": "Failed to connect to bus: No such file or directory",
    "passwd": "passwd: Authentication token manipulation error",
    "useradd": "useradd: Permission denied.",
    "userdel": "userdel: Permission denied.",
    "kill": "bash: kill: (1234) - Operation not permitted",
    "shutdown": "shutdown: Operation not permitted",
    "reboot": "reboot: Operation not permitted",
    "iptables": "iptables: Permission denied (you must be root)",
    "curl": "curl: (7) Failed to connect to localhost port 5090: Connection refused",
    "wget": "wget: unable to resolve host address",
    "ssh": "ssh: connect to host localhost port 22: Connection refused",
    "git": "fatal: not a git repository",
}


def mock_shell_execute(cmd: str, user: str) -> str:
    """Execute a command in the honey-pot mock shell.
    Returns realistic-looking error output. Logs the attempt."""
    pm = get_privilege_manager()
    entry = pm.record_breach(user, cmd, "honeypot")

    # Find matching mock response
    cmd_lower = cmd.lower().strip()
    for trigger, response in MOCK_RESPONSES.items():
        if trigger in cmd_lower:
            return response

    # Default fake response
    return f"bash: {cmd.split()[0]}: command not found\n"\
           f"bash: {cmd.split()[0]}: No such file or directory"


# ═══════════════════════════════════════════════════════════════════════════════
# COLD MIDDLEWARE DECORATOR
# ═══════════════════════════════════════════════════════════════════════════════

import subprocess as _subprocess


def run_as_user(cmd: str, user: str, timeout: int = 30) -> dict:
    """Run a shell command scoped to the correct OS user.
    - Owner: runs directly.
    - Guest: wrapped in bubblewrap (bwrap) namespace prison.
      Read-only bind mounts for /usr /lib /lib64 /bin /sbin.
      No network, no persistent storage, tmpfs /tmp, isolated PID/IPC/UTS.
      Falls back to sudo -u visitor if bwrap is not installed.
    """
    role = get_role(user)
    if CAP_LATENCY_BYPASS in role.capabilities:
        full_cmd = cmd
    else:
        # Build bwrap command — unprivileged namespace prison
        bwrap_prefix = (
            "bwrap "
            "--ro-bind /usr /usr "
            "--ro-bind-try /lib /lib "
            "--ro-bind-try /lib64 /lib64 "
            "--ro-bind-try /lib32 /lib32 "
            "--ro-bind-try /bin /bin "
            "--ro-bind-try /sbin /sbin "
            "--ro-bind-try /etc/alternatives /etc/alternatives "
            "--ro-bind-try /etc/ld.so.cache /etc/ld.so.cache "
            "--dir /tmp "
            "--proc /proc "
            "--dev /dev "
            "--tmpfs /home "
            "--unshare-all "
            "--new-session "
            "--die-with-parent "
            f"-- sh -c {_subprocess.list2cmdline([cmd])}"
        )
        # Check bwrap availability once (cached in module-level flag)
        if _bwrap_available():
            full_cmd = bwrap_prefix
        else:
            full_cmd = f"sudo -u visitor -- sh -c {_subprocess.list2cmdline([cmd])}"

    # OWNER-ONLY — single-user dev box
    import shlex
    try:
        args = shlex.split(full_cmd)
        r = _subprocess.run(
            args, capture_output=True, text=True, timeout=timeout
        )
        return {"exit": r.returncode, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
    except _subprocess.TimeoutExpired:
        return {"exit": -1, "stdout": "", "stderr": f"Timeout ({timeout}s)"}
    except Exception as e:
        return {"exit": -1, "stdout": "", "stderr": str(e)}


_bwrap_ok: Optional[bool] = None

def _bwrap_available() -> bool:
    global _bwrap_ok
    if _bwrap_ok is None:
        result = _subprocess.run(["which", "bwrap"], capture_output=True)
        _bwrap_ok = result.returncode == 0
        if not _bwrap_ok:
            print("[BWRAP] bubblewrap not found — falling back to sudo -u visitor")
    return _bwrap_ok


def cold_latency(user: str, confidence: float = 1.0):
    """Enforce progressive latency for guests based on role + suspicion level."""
    pm = get_privilege_manager()
    latency = pm.get_latency(user, confidence)
    if latency > 0:
        tone = pm.get_suspicion_tone(user)
        suspicion = pm._get_suspicion(user)
        print(f"[COLD] {user}: suspicion={suspicion:.1f}, tone={tone}, latency={latency:.1f}s")
        time.sleep(latency)


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

_pm: Optional[PrivilegeManager] = None


def get_privilege_manager() -> PrivilegeManager:
    global _pm
    if _pm is None:
        _pm = PrivilegeManager()
    return _pm
