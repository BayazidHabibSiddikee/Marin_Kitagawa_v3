#!/usr/bin/env python3
"""
OOM Priority Manager — prevents Out-of-Memory kills by managing service priorities.
When memory is low, kills less critical services before OOM killer strikes.
"""

import subprocess
import os
from typing import Dict, Any, List
from datetime import datetime

# Service priority tiers (lower number = higher priority = killed last)
# Tier 0: Never kill (core system)
# Tier 1: Kill only in emergency
# Tier 2: Kill when memory is low
# Tier 3: Kill first (most expendable)
SERVICE_TIERS = {
    # Tier 0 — never kill
    "lightdm.service":        0,
    "NetworkManager.service": 0,
    "ssh.service":            0,
    "cron.service":           0,
    "marin.service":          0,  # The AI itself

    # Tier 1 — kill only in emergency (< 200MB free)
    "ollama.service":         1,
    "marin-web.service":      1,
    "command-api.service":    1,

    # Tier 2 — kill when memory is low (< 500MB free)
    "rag.service":            2,

    # Tier 3 — kill first
    "docker.service":         3,
}

# Memory thresholds (MB)
THRESHOLD_CRITICAL = 200   # Kill tier 2+ services
THRESHOLD_LOW      = 500   # Kill tier 3 services
THRESHOLD_WARNING  = 1000  # Log warning


def _get_free_memory_mb() -> int:
    """Get available memory in MB."""
    try:
        r = subprocess.run(
            ["free", "-m"], capture_output=True, text=True, timeout=5
        )
        for line in r.stdout.splitlines():
            if line.startswith("Mem:"):
                parts = line.split()
                # free = total - used - buff/cache, but we want available
                available = int(parts[6]) if len(parts) > 6 else int(parts[3])
                return available
    except Exception:
        pass
    return 9999  # assume healthy if we can't read


def _get_service_memory(service: str) -> int:
    """Get memory usage of a service in MB."""
    try:
        r = subprocess.run(
            ["systemctl", "show", service, "--property=MemoryCurrent"],
            capture_output=True, text=True, timeout=5
        )
        for line in r.stdout.splitlines():
            if line.startswith("MemoryCurrent="):
                bytes_val = line.split("=")[1].strip()
                if bytes_val and bytes_val != "[not set]":
                    return int(bytes_val) // (1024 * 1024)
    except Exception:
        pass
    return 0


def check_memory() -> Dict[str, Any]:
    """Check memory status and kill services if needed."""
    free_mb = _get_free_memory_mb()
    killed = []
    status = "healthy"

    if free_mb < THRESHOLD_CRITICAL:
        status = "critical"
        # Kill tier 2+ services
        for service, tier in sorted(SERVICE_TIERS.items(), key=lambda x: -x[1]):
            if tier >= 2:
                try:
                    subprocess.run(
                        ["systemctl", "stop", service],
                        capture_output=True, timeout=10
                    )
                    killed.append(service)
                    print(f"[OOM] Killed tier {tier} service: {service}")
                except Exception:
                    pass
            if free_mb >= THRESHOLD_CRITICAL:
                break
            free_mb = _get_free_memory_mb()

    elif free_mb < THRESHOLD_LOW:
        status = "low"
        # Kill tier 3 services only
        for service, tier in sorted(SERVICE_TIERS.items(), key=lambda x: -x[1]):
            if tier >= 3:
                try:
                    subprocess.run(
                        ["systemctl", "stop", service],
                        capture_output=True, timeout=10
                    )
                    killed.append(service)
                    print(f"[OOM] Killed tier {tier} service: {service}")
                except Exception:
                    pass

    elif free_mb < THRESHOLD_WARNING:
        status = "warning"

    return {
        "status": status,
        "free_mb": free_mb,
        "killed": killed,
        "timestamp": datetime.now().isoformat(),
    }


def get_memory_report() -> Dict[str, Any]:
    """Get detailed memory report for all services."""
    free_mb = _get_free_memory_mb()
    services = {}
    for service, tier in SERVICE_TIERS.items():
        mem = _get_service_memory(service)
        active = _is_active(service)
        services[service] = {
            "tier": tier,
            "memory_mb": mem,
            "active": active,
        }
    return {
        "free_mb": free_mb,
        "status": "critical" if free_mb < THRESHOLD_CRITICAL else
                  "low" if free_mb < THRESHOLD_LOW else
                  "warning" if free_mb < THRESHOLD_WARNING else "healthy",
        "services": services,
    }


def _is_active(service: str) -> bool:
    try:
        r = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() == "active"
    except Exception:
        return False
