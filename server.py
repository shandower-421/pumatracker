"""PumaTracker Flask server."""

import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, g, make_response
from werkzeug.security import generate_password_hash, check_password_hash

# Use pbkdf2 for compatibility with Python < 3.12 (scrypt unavailable)
def hash_password(password):
    return generate_password_hash(password, method='pbkdf2:sha256')


import config
import db as database

app = Flask(__name__, static_folder='static', static_url_path='')
app.secret_key = config.SECRET_KEY


# ── Database lifecycle ──

@app.before_request
def before_request():
    g.db = database.get_db()
    # Periodically clean expired sessions (cheap no-op most of the time)
    g.db.execute("DELETE FROM sessions WHERE expires_at < datetime('now')")
    g.db.commit()


@app.teardown_appcontext
def close_db(exception):
    conn = g.pop('db', None)
    if conn is not None:
        conn.close()


# ── Auth helpers ──

def get_current_user():
    """Return the current user dict or None."""
    token = request.cookies.get('session_token')
    if not token:
        return None
    row = g.db.execute(
        "SELECT u.* FROM users u JOIN sessions s ON s.user_id = u.id "
        "WHERE s.token = ? AND s.expires_at > datetime('now')",
        (token,)
    ).fetchone()
    return database.dict_row(row)


def require_auth(f):
    """Decorator: reject with 401 if not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        g.user = user
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    """Decorator: reject with 403 if not admin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        if not user['is_admin']:
            return jsonify({'error': 'Forbidden'}), 403
        g.user = user
        return f(*args, **kwargs)
    return decorated


# ── Auth endpoints ──

@app.route('/api/auth/setup-required')
def auth_setup_required():
    """Check if initial setup is needed (no users exist)."""
    count = g.db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return jsonify({'setup_required': count == 0})


@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    """Register a new user. First user becomes admin. Others require admin."""
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    display_name = (data.get('display_name') or username).strip()

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    if len(username) > 50 or len(password) < 4:
        return jsonify({'error': 'Username max 50 chars, password min 4 chars'}), 400

    user_count = g.db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    is_first_user = user_count == 0

    # Only first user or admin can register
    if not is_first_user:
        current = get_current_user()
        if not current or not current['is_admin']:
            return jsonify({'error': 'Only admins can create accounts'}), 403

    try:
        cur = g.db.execute(
            "INSERT INTO users (username, display_name, password_hash, is_admin) VALUES (?, ?, ?, ?)",
            (username, display_name, hash_password(password), 1 if is_first_user else 0)
        )
        g.db.commit()
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username already taken'}), 409

    user_id = cur.lastrowid

    # Auto-login for first user
    if is_first_user:
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(days=config.SESSION_LIFETIME_DAYS)
        g.db.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires.isoformat())
        )
        g.db.commit()
        resp = make_response(jsonify({
            'id': user_id, 'username': username,
            'display_name': display_name, 'is_admin': True
        }))
        resp.set_cookie('session_token', token, httponly=True,
                        max_age=config.SESSION_LIFETIME_DAYS * 86400, samesite='Lax')
        return resp

    return jsonify({'id': user_id, 'username': username,
                    'display_name': display_name, 'is_admin': False}), 201


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    row = g.db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not row or not check_password_hash(row['password_hash'], password):
        return jsonify({'error': 'Invalid credentials'}), 401

    user = database.dict_row(row)
    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(days=config.SESSION_LIFETIME_DAYS)
    g.db.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user['id'], expires.isoformat())
    )
    g.db.commit()

    resp = make_response(jsonify({
        'id': user['id'], 'username': user['username'],
        'display_name': user['display_name'], 'is_admin': bool(user['is_admin'])
    }))
    resp.set_cookie('session_token', token, httponly=True,
                    max_age=config.SESSION_LIFETIME_DAYS * 86400, samesite='Lax')
    return resp


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    token = request.cookies.get('session_token')
    if token:
        g.db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        g.db.commit()
    resp = make_response(jsonify({'ok': True}))
    resp.delete_cookie('session_token')
    return resp


@app.route('/api/auth/me')
@require_auth
def auth_me():
    u = g.user
    return jsonify({
        'id': u['id'], 'username': u['username'],
        'display_name': u['display_name'], 'is_admin': bool(u['is_admin'])
    })


# ── User management (admin) ──

@app.route('/api/users')
@require_admin
def list_users():
    rows = g.db.execute(
        "SELECT id, username, display_name, is_admin, created_at FROM users ORDER BY id"
    ).fetchall()
    return jsonify(database.dict_rows(rows))


@app.route('/api/users/<int:user_id>', methods=['PATCH'])
@require_admin
def update_user(user_id):
    data = request.get_json() or {}
    user = g.db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return jsonify({'error': 'Not found'}), 404

    sets, vals = [], []
    if 'display_name' in data:
        sets.append("display_name = ?")
        vals.append(str(data['display_name']).strip()[:50])
    if 'is_admin' in data:
        sets.append("is_admin = ?")
        vals.append(1 if data['is_admin'] else 0)
    if 'password' in data and data['password']:
        sets.append("password_hash = ?")
        vals.append(hash_password(data['password']))
        # Invalidate target user's sessions to force re-login
        g.db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    if sets:
        vals.append(user_id)
        g.db.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", vals)
        g.db.commit()

    updated = database.dict_row(
        g.db.execute("SELECT id, username, display_name, is_admin, created_at FROM users WHERE id = ?",
                     (user_id,)).fetchone()
    )
    return jsonify(updated)


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@require_admin
def delete_user(user_id):
    if user_id == g.user['id']:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    g.db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    g.db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    g.db.commit()
    return jsonify({'ok': True})


# ── Groups (Projects) ──

@app.route('/api/groups')
@require_auth
def list_groups():
    rows = g.db.execute("""
        SELECT g.*, COUNT(t.id) AS task_count
        FROM groups g
        LEFT JOIN tasks t ON t.group_id = g.id AND t.archived = 0
        GROUP BY g.id
        ORDER BY g.position, g.id
    """).fetchall()
    return jsonify(database.dict_rows(rows))


@app.route('/api/groups', methods=['POST'])
@require_auth
def create_group():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400

    max_pos = g.db.execute("SELECT COALESCE(MAX(position), 0) FROM groups").fetchone()[0]
    now = datetime.utcnow().isoformat() + 'Z'
    cur = g.db.execute(
        "INSERT INTO groups (name, position, updated_at) VALUES (?, ?, ?)",
        (name, max_pos + 1, now)
    )
    g.db.commit()
    group = database.dict_row(
        g.db.execute("SELECT g.*, 0 AS task_count FROM groups g WHERE g.id = ?",
                     (cur.lastrowid,)).fetchone()
    )
    return jsonify(group), 201


@app.route('/api/groups/<int:group_id>', methods=['PATCH'])
@require_auth
def update_group(group_id):
    data = request.get_json() or {}
    row = g.db.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404

    sets, vals = [], []
    if 'name' in data:
        sets.append("name = ?")
        vals.append(str(data['name']).strip()[:200])
    if 'position' in data:
        sets.append("position = ?")
        vals.append(int(data['position']))
    sets.append("updated_at = ?")
    vals.append(datetime.utcnow().isoformat() + 'Z')
    vals.append(group_id)

    g.db.execute(f"UPDATE groups SET {', '.join(sets)} WHERE id = ?", vals)
    g.db.commit()

    updated = database.dict_row(g.db.execute("""
        SELECT g.*, COUNT(t.id) AS task_count
        FROM groups g LEFT JOIN tasks t ON t.group_id = g.id AND t.archived = 0
        WHERE g.id = ? GROUP BY g.id
    """, (group_id,)).fetchone())
    return jsonify(updated)


@app.route('/api/groups/<int:group_id>', methods=['DELETE'])
@require_auth
def delete_group(group_id):
    # Unlink tasks from this group (don't delete them)
    g.db.execute("UPDATE tasks SET group_id = NULL WHERE group_id = ?", (group_id,))
    g.db.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    g.db.commit()
    return jsonify({'ok': True})


# ── Tasks ──

GTD_RANK = {'Inbox': 0, 'Today': 1, 'Soon': 2, 'Waiting': 3, 'Someday': 4, 'On Hold': 5}


def hydrate_task(row):
    """Add group_name and assignee_name to a task row dict."""
    d = database.dict_row(row) if not isinstance(row, dict) else row
    # group_name comes from the JOIN
    if 'group_name' not in d:
        d['group_name'] = ''
    d['assignee_name'] = ''
    return d


@app.route('/api/tasks')
@require_auth
def list_tasks():
    filters = request.args
    query = """
        SELECT t.*, COALESCE(grp.name, '') AS group_name
        FROM tasks t
        LEFT JOIN groups grp ON grp.id = t.group_id
    """
    conditions = []
    params = []

    if filters.get('archived') == '1':
        conditions.append("t.archived = 1")
    else:
        conditions.append("t.archived = 0")

    if filters.get('gtd'):
        conditions.append("t.gtd = ?")
        params.append(filters['gtd'])
    if filters.get('priority'):
        conditions.append("t.priority = ?")
        params.append(filters['priority'])
    if filters.get('status'):
        conditions.append("t.status = ?")
        params.append(filters['status'])
    if filters.get('group_id'):
        conditions.append("t.group_id = ?")
        params.append(int(filters['group_id']))
    if filters.get('no_project'):
        conditions.append("t.group_id IS NULL")
    if filters.get('search'):
        q = f"%{filters['search']}%"
        conditions.append("(t.name LIKE ? OR t.description LIKE ? OR t.assignee_text LIKE ?)")
        params.extend([q, q, q])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    # Match the frontend sort: GTD rank, then position, then created_at desc
    query += " ORDER BY t.archived ASC"
    # We'll sort in Python to match the exact GTD_RANK logic
    rows = g.db.execute(query, params).fetchall()
    tasks = [hydrate_task(r) for r in rows]

    tasks.sort(key=lambda t: (
        GTD_RANK.get(t['gtd'], 5),
        t['position'] or 0,
        # Reverse created_at — negate by using descending string compare trick
        '' if not t.get('created_at') else t['created_at']
    ))
    # For the third sort key, we need descending created_at as tiebreaker
    # Re-sort properly with a stable sort approach
    tasks.sort(key=lambda t: (
        GTD_RANK.get(t['gtd'], 5),
        t['position'] or 0,
    ))

    return jsonify(tasks)


@app.route('/api/tasks/counts')
@require_auth
def task_counts():
    rows = g.db.execute("SELECT gtd, priority, archived, group_id FROM tasks").fetchall()
    c = {
        'all_tasks': 0, 'today': 0, 'inbox': 0, 'soon': 0,
        'waiting': 0, 'someday': 0, 'hold': 0,
        'high': 0, 'medium': 0, 'low': 0,
        'archived': 0, 'no_project': 0
    }
    gtd_map = {'Today': 'today', 'Inbox': 'inbox', 'Soon': 'soon',
               'Waiting': 'waiting', 'Someday': 'someday', 'On Hold': 'hold'}
    prio_map = {'High': 'high', 'Medium': 'medium', 'Low': 'low'}

    for r in rows:
        if r['archived']:
            c['archived'] += 1
            continue
        c['all_tasks'] += 1
        if not r['group_id']:
            c['no_project'] += 1
        gk = gtd_map.get(r['gtd'])
        if gk:
            c[gk] += 1
        pk = prio_map.get(r['priority'])
        if pk:
            c[pk] += 1

    return jsonify(c)


@app.route('/api/tasks', methods=['POST'])
@require_auth
def create_task():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400

    now = datetime.utcnow().isoformat() + 'Z'
    gtd = data.get('gtd', 'Inbox')
    if gtd not in database.VALID_GTD:
        gtd = 'Inbox'
    priority = data.get('priority', '')
    if priority not in database.VALID_PRIORITY:
        priority = ''

    group_id = data.get('group_id')
    if group_id is not None:
        try:
            group_id = int(group_id)
        except (TypeError, ValueError):
            group_id = None

    parent_id = data.get('parent_id')
    if parent_id is not None:
        try:
            parent_id = int(parent_id)
        except (TypeError, ValueError):
            parent_id = None

    cur = g.db.execute("""
        INSERT INTO tasks (name, status, priority, gtd, group_id, parent_id,
                           due, done, archived, position, recurrence,
                           assignee_text, url, description, created_at, updated_at)
        VALUES (?, 'Not Started', ?, ?, ?, ?, '', 0, 0, 0, '', '', '', '', ?, ?)
    """, (name, priority, gtd, group_id, parent_id, now, now))
    g.db.commit()

    task = database.dict_row(g.db.execute("""
        SELECT t.*, COALESCE(grp.name, '') AS group_name
        FROM tasks t LEFT JOIN groups grp ON grp.id = t.group_id
        WHERE t.id = ?
    """, (cur.lastrowid,)).fetchone())
    task['assignee_name'] = ''
    return jsonify(task), 201


@app.route('/api/tasks/<int:task_id>', methods=['PATCH'])
@require_auth
def update_task(task_id):
    data = request.get_json() or {}
    row = g.db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404

    task = database.dict_row(row)
    now = datetime.utcnow().isoformat() + 'Z'

    FIELDS = ['name', 'status', 'priority', 'gtd', 'due', 'done', 'description',
              'url', 'group_id', 'position', 'archived', 'parent_id', 'recurrence']
    sets = []
    vals = []

    for f in FIELDS:
        if f in data:
            sets.append(f"{f} = ?")
            vals.append(data[f])
            task[f] = data[f]

    if 'assignee' in data:
        sets.append("assignee_text = ?")
        val = (data['assignee'] or '').strip()
        vals.append(val)
        task['assignee_text'] = val

    if 'status' in data:
        done_val = 1 if data['status'] == 'Completed' else 0
        sets.append("done = ?")
        vals.append(done_val)
        task['done'] = done_val

    sets.append("updated_at = ?")
    vals.append(now)
    task['updated_at'] = now
    vals.append(task_id)

    g.db.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", vals)

    # Spawn recurrence if completed
    recurrence_spawned = False
    if data.get('status') == 'Completed' and task.get('recurrence'):
        nd = database.next_due(task['recurrence'], task.get('due', ''))
        if nd:
            g.db.execute("""
                INSERT INTO tasks (name, status, priority, gtd, group_id, parent_id,
                                   due, done, archived, position, recurrence,
                                   assignee_text, url, description, created_at, updated_at)
                VALUES (?, 'Not Started', ?, ?, ?, ?, ?, 0, 0, 0, ?, ?, '', '', ?, ?)
            """, (task['name'], task.get('priority', ''), task.get('gtd', 'Inbox'),
                  task.get('group_id'), task.get('parent_id'),
                  nd, task.get('recurrence', ''), task.get('assignee_text', ''),
                  now, now))
            recurrence_spawned = True

    g.db.commit()

    result = database.dict_row(g.db.execute("""
        SELECT t.*, COALESCE(grp.name, '') AS group_name
        FROM tasks t LEFT JOIN groups grp ON grp.id = t.group_id
        WHERE t.id = ?
    """, (task_id,)).fetchone())
    result['assignee_name'] = ''
    result['recurrence_spawned'] = recurrence_spawned
    return jsonify(result)


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@require_auth
def delete_task(task_id):
    # CASCADE will handle subtasks and notes
    g.db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    g.db.commit()
    return jsonify({'ok': True})


@app.route('/api/tasks/archive', methods=['POST'])
@require_auth
def archive_completed():
    now = datetime.utcnow().isoformat() + 'Z'
    cur = g.db.execute(
        "UPDATE tasks SET archived = 1, updated_at = ? WHERE status = 'Completed' AND archived = 0",
        (now,)
    )
    g.db.commit()
    return jsonify({'ok': True, 'count': cur.rowcount})


@app.route('/api/tasks/reorder', methods=['POST'])
@require_auth
def reorder():
    data = request.get_json() or {}

    task_updates = data.get('tasks', [])
    group_updates = data.get('groups', [])

    for u in task_updates:
        sets, vals = [], []
        if 'gtd' in u:
            sets.append("gtd = ?")
            vals.append(u['gtd'])
        if 'position' in u:
            sets.append("position = ?")
            vals.append(int(u['position']))
        if sets:
            vals.append(int(u['id']))
            g.db.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", vals)

    for u in group_updates:
        if 'position' in u:
            g.db.execute("UPDATE groups SET position = ? WHERE id = ?",
                         (int(u['position']), int(u['id'])))

    g.db.commit()
    return jsonify({'ok': True})


# ── Notes (Comments) ──

@app.route('/api/tasks/<int:task_id>/notes')
@require_auth
def list_notes(task_id):
    rows = g.db.execute("""
        SELECT n.*, COALESCE(u.display_name, u.username, 'Unknown') AS username
        FROM notes n
        LEFT JOIN users u ON u.id = n.user_id
        WHERE n.task_id = ?
        ORDER BY n.created_at DESC
    """, (task_id,)).fetchall()
    return jsonify(database.dict_rows(rows))


@app.route('/api/tasks/<int:task_id>/notes', methods=['POST'])
@require_auth
def create_note(task_id):
    data = request.get_json() or {}
    body = (data.get('body') or '').strip()
    if not body:
        return jsonify({'error': 'Body required'}), 400

    # Verify task exists
    task = g.db.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    now = datetime.utcnow().isoformat() + 'Z'
    cur = g.db.execute(
        "INSERT INTO notes (task_id, user_id, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (task_id, g.user['id'], body, now, now)
    )
    g.db.commit()

    note = database.dict_row(g.db.execute("""
        SELECT n.*, COALESCE(u.display_name, u.username, 'Unknown') AS username
        FROM notes n LEFT JOIN users u ON u.id = n.user_id
        WHERE n.id = ?
    """, (cur.lastrowid,)).fetchone())
    return jsonify(note), 201


# ── Data export/import ──

@app.route('/api/data/export')
@require_auth
def export_data():
    tasks = database.dict_rows(g.db.execute("SELECT * FROM tasks").fetchall())
    groups = database.dict_rows(g.db.execute("SELECT * FROM groups").fetchall())
    notes = database.dict_rows(g.db.execute("""
        SELECT n.*, COALESCE(u.display_name, u.username, 'Unknown') AS username
        FROM notes n LEFT JOIN users u ON u.id = n.user_id
    """).fetchall())
    return jsonify({
        'version': 2,
        'exported': datetime.utcnow().isoformat() + 'Z',
        'tasks': tasks,
        'groups': groups,
        'notes': notes,
    })


@app.route('/api/data/import', methods=['POST'])
@require_auth
def import_data():
    """Import data — inserts all records (new IDs assigned by DB)."""
    data = request.get_json() or {}
    if not isinstance(data.get('tasks'), list) or not isinstance(data.get('groups'), list):
        return jsonify({'error': 'Invalid format: need tasks and groups arrays'}), 400
    notes_list = data.get('notes', [])
    if not isinstance(notes_list, list):
        notes_list = []

    stats = {'groups_added': 0, 'tasks_added': 0, 'notes_added': 0}

    # Import groups, track old→new ID mapping
    group_id_map = {}
    for raw_g in data['groups']:
        sg = database.sanitize_group(raw_g)
        cur = g.db.execute(
            "INSERT INTO groups (name, position, updated_at) VALUES (?, ?, ?)",
            (sg['name'], sg['position'], sg['updated_at'])
        )
        old_id = raw_g.get('id')
        if old_id is not None:
            group_id_map[int(old_id)] = cur.lastrowid
        stats['groups_added'] += 1

    # Import tasks, track old→new ID mapping
    task_id_map = {}
    for raw_t in data['tasks']:
        st = database.sanitize_task(raw_t)
        # Remap group_id
        if st['group_id'] and st['group_id'] in group_id_map:
            st['group_id'] = group_id_map[st['group_id']]
        elif st['group_id'] and st['group_id'] not in group_id_map:
            st['group_id'] = None  # orphaned reference

        cur = g.db.execute("""
            INSERT INTO tasks (name, status, priority, gtd, group_id, parent_id,
                               due, done, archived, position, recurrence,
                               assignee_text, url, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (st['name'], st['status'], st['priority'], st['gtd'], st['group_id'],
              st['due'], st['done'], st['archived'], st['position'], st['recurrence'],
              st['assignee_text'], st['url'], st['description'],
              st['created_at'], st['updated_at']))

        old_id = raw_t.get('id')
        if old_id is not None:
            task_id_map[int(old_id)] = cur.lastrowid
        stats['tasks_added'] += 1

    # Fix up parent_id references now that we have the mapping
    for raw_t in data['tasks']:
        old_parent = raw_t.get('parent_id')
        if old_parent is not None:
            old_id = raw_t.get('id')
            if old_id is not None and int(old_id) in task_id_map and int(old_parent) in task_id_map:
                new_task_id = task_id_map[int(old_id)]
                new_parent_id = task_id_map[int(old_parent)]
                g.db.execute("UPDATE tasks SET parent_id = ? WHERE id = ?",
                             (new_parent_id, new_task_id))

    # Import notes
    for raw_n in notes_list:
        sn = database.sanitize_note(raw_n)
        # Remap task_id
        if sn['task_id'] in task_id_map:
            sn['task_id'] = task_id_map[sn['task_id']]
        else:
            continue  # skip orphaned notes

        g.db.execute(
            "INSERT INTO notes (task_id, user_id, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (sn['task_id'], g.user['id'], sn['body'], sn['created_at'], sn['updated_at'])
        )
        stats['notes_added'] += 1

    g.db.commit()
    return jsonify({'ok': True, 'stats': stats})


# ── Password change (any user) ──

@app.route('/api/auth/password', methods=['POST'])
@require_auth
def change_password():
    data = request.get_json() or {}
    current = data.get('current_password', '')
    new_pw = data.get('new_password', '')

    if not current or not new_pw:
        return jsonify({'error': 'Current and new password required'}), 400
    if len(new_pw) < 4:
        return jsonify({'error': 'New password must be at least 4 characters'}), 400

    row = g.db.execute("SELECT * FROM users WHERE id = ?", (g.user['id'],)).fetchone()
    if not check_password_hash(row['password_hash'], current):
        return jsonify({'error': 'Current password is incorrect'}), 401

    g.db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                 (hash_password(new_pw), g.user['id']))
    g.db.commit()
    return jsonify({'ok': True})


# ── Backups (admin) ──

@app.route('/api/backups')
@require_admin
def list_backups_route():
    import backup
    return jsonify(backup.list_backups())


@app.route('/api/backups', methods=['POST'])
@require_admin
def create_backup_route():
    import backup
    result = backup.create_backup()
    if result:
        return jsonify({'ok': True, 'filename': result})
    return jsonify({'error': 'Backup failed'}), 500


@app.route('/api/backups/<filename>/restore', methods=['POST'])
@require_admin
def restore_backup_route(filename):
    import backup
    if backup.restore_backup(filename):
        return jsonify({'ok': True})
    return jsonify({'error': 'Restore failed — file not found or invalid'}), 400


@app.route('/api/backups/<filename>', methods=['DELETE'])
@require_admin
def delete_backup_route(filename):
    import backup
    if backup.delete_backup(filename):
        return jsonify({'ok': True})
    return jsonify({'error': 'Delete failed'}), 400


# ── Static file serving ──

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/login')
def serve_login():
    return send_from_directory(app.static_folder, 'login.html')


# ── Startup ──

if __name__ == '__main__':
    database.init_db()
    import backup
    backup.start_scheduler()
    print(f"PumaTracker server starting on http://{config.HOST}:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, debug=os.environ.get('FLASK_DEBUG') == '1')
