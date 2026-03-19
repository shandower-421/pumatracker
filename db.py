"""Database initialization, schema, and helpers for PumaTracker."""

import os
import sqlite3
from datetime import datetime, timedelta

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Not Started',
    priority TEXT NOT NULL DEFAULT '',
    gtd TEXT NOT NULL DEFAULT 'Inbox',
    group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    parent_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    due TEXT NOT NULL DEFAULT '',
    done INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0,
    recurrence TEXT NOT NULL DEFAULT '',
    assignee_text TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_db():
    """Get a database connection. Caller must close it."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def dict_row(row):
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return None
    return dict(row)


def dict_rows(rows):
    """Convert a list of sqlite3.Row to a list of dicts."""
    return [dict(r) for r in rows]


# ── Recurrence helper (ported from JS) ──

def next_due(recurrence, due_str):
    """Calculate the next due date for a recurring task."""
    if not recurrence:
        return None
    try:
        d = datetime.strptime(due_str, '%Y-%m-%d') if due_str else datetime.now()
    except ValueError:
        d = datetime.now()

    if recurrence == 'daily':
        d += timedelta(days=1)
    elif recurrence == 'weekly':
        d += timedelta(days=7)
    elif recurrence == 'monthly':
        day = d.day
        if d.month == 12:
            d = d.replace(year=d.year + 1, month=1, day=1)
        else:
            d = d.replace(month=d.month + 1, day=1)
        # Try to keep same day, clamp to end of month
        import calendar
        max_day = calendar.monthrange(d.year, d.month)[1]
        d = d.replace(day=min(day, max_day))
    elif recurrence == 'yearly':
        try:
            d = d.replace(year=d.year + 1)
        except ValueError:
            # Feb 29 → Feb 28
            d = d.replace(year=d.year + 1, day=28)
    else:
        return None

    return d.strftime('%Y-%m-%d')


# ── Sanitization (ported from JS sanitizeImport) ──

VALID_GTD = {'Inbox', 'Today', 'Soon', 'Waiting', 'Someday', 'On Hold'}
VALID_STATUS = {'Not Started', 'In Progress', 'Completed'}
VALID_PRIORITY = {'', 'CRIT', 'High', 'Medium', 'Low', 'Info'}
VALID_RECURRENCE = {'', 'daily', 'weekly', 'monthly', 'yearly'}


def sanitize_task(t):
    """Sanitize a task dict from import data."""
    def _int(v, default=0):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    def _intornull(v):
        try:
            val = int(v)
            return val if val else None
        except (TypeError, ValueError):
            return None

    now = datetime.utcnow().isoformat() + 'Z'
    return {
        'name': str(t.get('name', ''))[:500],
        'status': t.get('status', 'Not Started') if t.get('status') in VALID_STATUS else 'Not Started',
        'priority': t.get('priority', '') if t.get('priority') in VALID_PRIORITY else '',
        'gtd': t.get('gtd', 'Inbox') if t.get('gtd') in VALID_GTD else 'Inbox',
        'recurrence': t.get('recurrence', '') if t.get('recurrence') in VALID_RECURRENCE else '',
        'group_id': _intornull(t.get('group_id')),
        'parent_id': _intornull(t.get('parent_id')),
        'due': t.get('due', '') if isinstance(t.get('due'), str) and len(t.get('due', '')) == 10 else '',
        'done': 1 if t.get('done') else 0,
        'archived': 1 if t.get('archived') else 0,
        'position': _int(t.get('position', 0)),
        'assignee_text': str(t.get('assignee_text', ''))[:200],
        'url': str(t.get('url', ''))[:2000],
        'description': str(t.get('description', ''))[:10000],
        'created_at': str(t.get('created_at', now)),
        'updated_at': str(t.get('updated_at', t.get('created_at', now))),
    }


def sanitize_group(g):
    """Sanitize a group dict from import data."""
    now = datetime.utcnow().isoformat() + 'Z'
    try:
        pos = int(g.get('position', 0))
    except (TypeError, ValueError):
        pos = 0
    return {
        'name': str(g.get('name', ''))[:200],
        'position': pos,
        'updated_at': str(g.get('updated_at', now)),
    }


def sanitize_note(n):
    """Sanitize a note dict from import data."""
    now = datetime.utcnow().isoformat() + 'Z'
    return {
        'body': str(n.get('body', ''))[:10000],
        'task_id': int(n.get('task_id', 0)),
        'created_at': str(n.get('created_at', now)),
        'updated_at': str(n.get('updated_at', n.get('created_at', now))),
    }
