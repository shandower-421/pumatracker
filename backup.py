"""Rotating SQLite backup system for PumaTracker."""

import os
import sqlite3
import threading
from datetime import datetime

import config


def create_backup():
    """Create a backup of the database. Returns the backup filename or None on error."""
    if not os.path.exists(config.DB_PATH):
        return None

    os.makedirs(config.BACKUP_DIR, exist_ok=True)
    timestamp = datetime.utcnow().strftime('%Y-%m-%d-%H%M%S')
    backup_name = f'pumatracker-{timestamp}.db'
    backup_path = os.path.join(config.BACKUP_DIR, backup_name)

    try:
        src = sqlite3.connect(config.DB_PATH)
        dst = sqlite3.connect(backup_path)
        src.backup(dst)
        dst.close()
        src.close()
        _rotate_backups()
        return backup_name
    except Exception as e:
        print(f'[backup] Error creating backup: {e}')
        return None


def _rotate_backups():
    """Delete oldest backups if count exceeds BACKUP_MAX_COUNT."""
    if not os.path.isdir(config.BACKUP_DIR):
        return

    backups = sorted(
        [f for f in os.listdir(config.BACKUP_DIR) if f.startswith('pumatracker-') and f.endswith('.db')],
        reverse=True  # newest first
    )

    while len(backups) > config.BACKUP_MAX_COUNT:
        oldest = backups.pop()
        try:
            os.remove(os.path.join(config.BACKUP_DIR, oldest))
        except OSError:
            pass


def list_backups():
    """Return a list of backup info dicts, newest first."""
    if not os.path.isdir(config.BACKUP_DIR):
        return []

    backups = []
    for f in os.listdir(config.BACKUP_DIR):
        if f.startswith('pumatracker-') and f.endswith('.db'):
            path = os.path.join(config.BACKUP_DIR, f)
            stat = os.stat(path)
            backups.append({
                'filename': f,
                'size_bytes': stat.st_size,
                'created_at': datetime.utcfromtimestamp(stat.st_mtime).isoformat() + 'Z',
            })

    backups.sort(key=lambda b: b['filename'], reverse=True)
    return backups


def _safe_backup_path(filename):
    """Validate a backup filename and return the full path, or None if invalid."""
    if not filename.startswith('pumatracker-') or not filename.endswith('.db'):
        return None
    if '/' in filename or '\\' in filename or '..' in filename:
        return None
    path = os.path.join(config.BACKUP_DIR, filename)
    if not os.path.realpath(path).startswith(os.path.realpath(config.BACKUP_DIR)):
        return None
    return path


def restore_backup(filename):
    """Restore a backup by replacing the current database. Returns True on success."""
    backup_path = _safe_backup_path(filename)
    if not backup_path or not os.path.exists(backup_path):
        return False

    try:
        # Create a safety backup before restoring
        create_backup()

        src = sqlite3.connect(backup_path)
        dst = sqlite3.connect(config.DB_PATH)
        src.backup(dst)
        dst.close()
        src.close()
        return True
    except Exception as e:
        print(f'[backup] Error restoring backup: {e}')
        return False


def delete_backup(filename):
    """Delete a specific backup file. Returns True on success."""
    path = _safe_backup_path(filename)
    if not path or not os.path.exists(path):
        return False
    try:
        os.remove(path)
        return True
    except OSError:
        return False


# ── Scheduled backup thread ──

_timer = None


def _schedule_next():
    """Schedule the next periodic backup."""
    global _timer
    interval = config.BACKUP_INTERVAL_HOURS * 3600
    _timer = threading.Timer(interval, _run_scheduled)
    _timer.daemon = True
    _timer.start()


def _run_scheduled():
    """Run a scheduled backup and schedule the next one."""
    result = create_backup()
    if result:
        print(f'[backup] Scheduled backup created: {result}')
    _schedule_next()


def start_scheduler():
    """Create an initial backup and start the periodic backup scheduler."""
    result = create_backup()
    if result:
        print(f'[backup] Startup backup created: {result}')
    _schedule_next()
    print(f'[backup] Scheduler started (every {config.BACKUP_INTERVAL_HOURS}h, keeping {config.BACKUP_MAX_COUNT} max)')
