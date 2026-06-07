#!/usr/bin/env python3
"""
Marin OS — Data Retention Cleanup
Deletes logs, temp files, and old data older than 14 days.
Runs daily via cron.
"""

import os
import glob
import logging
from pathlib import Path
from datetime import datetime, timedelta

RETENTION_DAYS = 14
MARIN_HOME = Path.home()
LOG_DIR = MARIN_HOME / "logs"
CACHE_DIR = MARIN_HOME / ".cache"

logging.basicConfig(
    filename=str(LOG_DIR / "cleanup.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("cleanup")


def cleanup_dir(directory: Path, patterns: list[str], days: int = RETENTION_DAYS):
    """Delete files matching patterns older than N days."""
    if not directory.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=days)
    removed = 0

    for pattern in patterns:
        for f in directory.rglob(pattern):
            if f.is_file():
                try:
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    if mtime < cutoff:
                        f.unlink()
                        removed += 1
                except Exception:
                    pass

    return removed


def main():
    log.info("Starting retention cleanup ({} days)".format(RETENTION_DAYS))
    total = 0

    # Logs
    count = cleanup_dir(LOG_DIR, ["*.log", "*.log.*"])
    log.info(f"Removed {count} old log files")
    total += count

    # Cache
    count = cleanup_dir(CACHE_DIR, ["*"], days=7)
    log.info(f"Removed {count} old cache files")
    total += count

    # Temp files
    for d in [MARIN_HOME / ".local" / "share" / "Trash", Path("/tmp")]:
        count = cleanup_dir(d, ["marin_*", "*.tmp"], days=7)
        total += count

    # Compress large logs (keep last 14 days, compress older)
    for log_file in LOG_DIR.glob("*.log"):
        if log_file.stat().st_size > 10 * 1024 * 1024:  # > 10MB
            try:
                import gzip
                with open(log_file, 'rb') as f_in:
                    with gzip.open(str(log_file) + '.gz', 'wb') as f_out:
                        f_out.writelines(f_in)
                log_file.unlink()
                log.info(f"Compressed {log_file.name}")
            except Exception:
                pass

    log.info(f"Cleanup complete: {total} items removed")
    print(f"Cleanup: {total} items removed (>{RETENTION_DAYS} days)")


if __name__ == "__main__":
    main()
