"""
PumaTracker - Flask Web App
Run with: python app.py
         python app.py --port 9000
         (or set "port" in config.json)
Then open http://localhost:8080 in your browser (or whichever port you chose).
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, functools, argparse, json
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'change-this-to-a-random-string-in-production'

DB = 'pumatracker.db'

# ─────────────────────────────────────────────
# DATABASE HELPERS
# ─────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row   # lets us access columns by name
    return conn

def init_db():
    """Create tables if they don't exist, and create the default admin account."""
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                active   INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS task_groups (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id   INTEGER NOT NULL,
                name       TEXT NOT NULL,
                position   INTEGER DEFAULT 0,
                FOREIGN KEY (owner_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id      INTEGER NOT NULL,
                name          TEXT NOT NULL,
                status        TEXT DEFAULT "Not Started",
                priority      TEXT DEFAULT "",
                gtd           TEXT DEFAULT "Inbox",
                assignee_id   INTEGER,
                assignee_text TEXT DEFAULT "",
                description   TEXT DEFAULT "",
                url           TEXT DEFAULT "",
                due           TEXT DEFAULT "",
                done          INTEGER DEFAULT 0,
                archived      INTEGER DEFAULT 0,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id)    REFERENCES users(id),
                FOREIGN KEY (assignee_id) REFERENCES users(id)
            );
        ''')

        # Migration: add active column if it doesn't exist yet
        try:
            db.execute('ALTER TABLE users ADD COLUMN active INTEGER DEFAULT 1')
            db.execute('UPDATE users SET active = 1 WHERE active IS NULL')
            db.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            db.execute('ALTER TABLE tasks ADD COLUMN assignee_text TEXT DEFAULT ""')
            db.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            db.execute('ALTER TABLE tasks ADD COLUMN description TEXT DEFAULT ""')
            db.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            db.execute('ALTER TABLE tasks ADD COLUMN url TEXT DEFAULT ""')
            db.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            db.execute('ALTER TABLE tasks ADD COLUMN group_id INTEGER DEFAULT NULL')
            db.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            db.execute('ALTER TABLE tasks ADD COLUMN position INTEGER DEFAULT 0')
            db.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            db.execute('ALTER TABLE tasks ADD COLUMN archived INTEGER DEFAULT 0')
            db.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Migration: rename status values to new labels
        db.execute("UPDATE tasks SET status = 'Not Started' WHERE status = 'To Do'")
        db.execute("UPDATE tasks SET status = 'Completed'   WHERE status = 'Done'")
        db.commit()

        # Create default admin if no users exist
        row = db.execute('SELECT COUNT(*) as c FROM users').fetchone()
        if row['c'] == 0:
            db.execute(
                'INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)',
                ('admin', generate_password_hash('admin', method='pbkdf2:sha256'))
            )
            db.commit()
            print("✅ Created default admin account: username=admin password=admin")
            print("   ⚠️  Please change the admin password after first login!")

# ─────────────────────────────────────────────
# AUTH HELPERS
# ─────────────────────────────────────────────

def login_required(f):
    """Decorator: redirect to login if not logged in."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    """Decorator: redirect to home if not admin."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────────
# AUTH ROUTES
# ─────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        with get_db() as db:
            user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user and check_password_hash(user['password'], password):
            if not user['active']:
                flash('This account has been disabled. Please contact an admin.', 'error')
                return render_template('login.html')
            session['user_id']  = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            return redirect(url_for('index'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    with get_db() as db:
        users = db.execute('SELECT id, username FROM users WHERE active = 1 ORDER BY username').fetchall()
    return render_template('index.html', users=users)

# ─────────────────────────────────────────────
# TASK API (JSON endpoints)
# ─────────────────────────────────────────────

@app.route('/api/tasks')
@login_required
def get_tasks():
    view      = request.args.get('view', 'all')
    f_prio    = request.args.get('priority', '')
    f_status  = request.args.get('status', '')
    f_gtd     = request.args.get('gtd', '')
    f_group   = request.args.get('group_id', '')
    archived  = request.args.get('archived', '0')
    uid       = session['user_id']

    query  = 'SELECT t.*, u.username as assignee_name FROM tasks t LEFT JOIN users u ON t.assignee_id = u.id WHERE t.owner_id = ?'
    # Note: group_id, position, archived are included via t.*
    params = [uid]

    # Archive view shows only archived; main dashboard hides archived
    if archived == '1':
        query += ' AND t.archived = 1'
    else:
        query += ' AND (t.archived = 0 OR t.archived IS NULL)'

    view_filters = {
        'today':   ('t.gtd = ?', 'Today'),
        'inbox':   ('t.gtd = ?', 'Inbox'),
        'soon':    ('t.gtd = ?', 'Soon'),
        'waiting': ('t.gtd = ?', 'Waiting'),
        'hold':    ('t.gtd = ?', 'On Hold'),
        'high':    ('t.priority = ?', 'High'),
        'medium':  ('t.priority = ?', 'Medium'),
        'low':     ('t.priority = ?', 'Low'),
    }
    if view in view_filters:
        clause, val = view_filters[view]
        query += f' AND {clause}'
        params.append(val)

    if f_prio:   query += ' AND t.priority = ?';  params.append(f_prio)
    if f_status: query += ' AND t.status = ?';    params.append(f_status)
    if f_gtd:    query += ' AND t.gtd = ?';       params.append(f_gtd)
    if f_group:  query += ' AND t.group_id = ?';  params.append(int(f_group))

    query += ' ORDER BY (t.group_id IS NULL) DESC, t.group_id, t.position, t.created_at DESC'

    with get_db() as db:
        tasks = db.execute(query, params).fetchall()

    return jsonify([dict(t) for t in tasks])

@app.route('/api/tasks', methods=['POST'])
@login_required
def create_task():
    data = request.json
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    with get_db() as db:
        cur = db.execute(
            'INSERT INTO tasks (owner_id, name, priority) VALUES (?, ?, ?)',
            (session['user_id'], name, '')
        )
        db.commit()
        task = db.execute(
            'SELECT t.*, u.username as assignee_name FROM tasks t LEFT JOIN users u ON t.assignee_id = u.id WHERE t.id = ?',
            (cur.lastrowid,)
        ).fetchone()
    return jsonify(dict(task)), 201

@app.route('/api/tasks/<int:task_id>', methods=['PATCH'])
@login_required
def update_task(task_id):
    data   = request.json
    uid    = session['user_id']
    fields = ['name', 'status', 'priority', 'gtd', 'assignee_id', 'due', 'done', 'description', 'url', 'group_id', 'position', 'archived']
    sets, params = [], []

    for f in fields:
        if f in data:
            sets.append(f'{f} = ?')
            params.append(data[f])

    # Handle free-text assignee: link to account if username matches an active user,
    # otherwise store as plain text and clear any linked account.
    if 'assignee' in data:
        val = (data['assignee'] or '').strip()
        with get_db() as db_lookup:
            match = db_lookup.execute(
                'SELECT id FROM users WHERE username = ? AND active = 1', (val,)
            ).fetchone() if val else None
        if match:
            sets += ['assignee_id = ?', 'assignee_text = ?']
            params += [match['id'], '']
        else:
            sets += ['assignee_id = ?', 'assignee_text = ?']
            params += [None, val]

    # Auto-sync done flag with status
    if 'status' in data:
        sets.append('done = ?')
        params.append(1 if data['status'] == 'Completed' else 0)

    if not sets:
        return jsonify({'error': 'Nothing to update'}), 400

    params += [task_id, uid]
    with get_db() as db:
        db.execute(
            f'UPDATE tasks SET {", ".join(sets)} WHERE id = ? AND owner_id = ?',
            params
        )
        db.commit()
        task = db.execute(
            'SELECT t.*, u.username as assignee_name FROM tasks t LEFT JOIN users u ON t.assignee_id = u.id WHERE t.id = ?',
            (task_id,)
        ).fetchone()
    if not task:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(task))

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    with get_db() as db:
        db.execute('DELETE FROM tasks WHERE id = ? AND owner_id = ?', (task_id, session['user_id']))
        db.commit()
    return jsonify({'ok': True})

@app.route('/api/tasks/<int:task_id>/assign', methods=['POST'])
@login_required
def assign_task(task_id):
    """Copy a task into another user's inbox."""
    data        = request.json
    target_id   = data.get('user_id')
    if not target_id:
        return jsonify({'error': 'user_id required'}), 400

    with get_db() as db:
        original = db.execute(
            'SELECT * FROM tasks WHERE id = ? AND owner_id = ?',
            (task_id, session['user_id'])
        ).fetchone()
        if not original:
            return jsonify({'error': 'Task not found'}), 404

        target = db.execute('SELECT id, username FROM users WHERE id = ?', (target_id,)).fetchone()
        if not target:
            return jsonify({'error': 'Target user not found'}), 404

        # Create a copy in the target user's inbox
        db.execute(
            '''INSERT INTO tasks (owner_id, name, priority, gtd, assignee_id, due, status)
               VALUES (?, ?, ?, "Inbox", ?, ?, ?)''',
            (target_id, original['name'], original['priority'],
             session['user_id'], original['due'], 'To Do')
        )
        db.commit()

    return jsonify({'ok': True, 'sent_to': target['username']})

@app.route('/api/counts')
@login_required
def get_counts():
    uid = session['user_id']
    with get_db() as db:
        rows = db.execute(
            '''SELECT
                SUM(archived=0 OR archived IS NULL) as all_tasks,
                SUM(gtd="Today"   AND (archived=0 OR archived IS NULL)) as today,
                SUM(gtd="Inbox"   AND (archived=0 OR archived IS NULL)) as inbox,
                SUM(gtd="Soon"    AND (archived=0 OR archived IS NULL)) as soon,
                SUM(gtd="Waiting" AND (archived=0 OR archived IS NULL)) as waiting,
                SUM(gtd="On Hold" AND (archived=0 OR archived IS NULL)) as hold,
                SUM(priority="High"   AND (archived=0 OR archived IS NULL)) as high,
                SUM(priority="Medium" AND (archived=0 OR archived IS NULL)) as medium,
                SUM(priority="Low"    AND (archived=0 OR archived IS NULL)) as low,
                SUM(archived=1) as archived
               FROM tasks WHERE owner_id = ?''',
            (uid,)
        ).fetchone()
    return jsonify(dict(rows))

@app.route('/api/archive', methods=['POST'])
@login_required
def archive_completed():
    uid = session['user_id']
    with get_db() as db:
        cur = db.execute(
            "UPDATE tasks SET archived = 1 WHERE owner_id = ? AND status = 'Completed' AND (archived = 0 OR archived IS NULL)",
            (uid,)
        )
        db.commit()
    return jsonify({'ok': True, 'count': cur.rowcount})

# ─────────────────────────────────────────────
# PROJECT API
# ─────────────────────────────────────────────

@app.route('/api/projects')
@login_required
def get_projects():
    uid = session['user_id']
    with get_db() as db:
        rows = db.execute(
            '''SELECT g.*, COUNT(t.id) as task_count
               FROM task_groups g
               LEFT JOIN tasks t ON t.group_id = g.id
               WHERE g.owner_id = ?
               GROUP BY g.id
               ORDER BY g.position''',
            (uid,)
        ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/projects', methods=['POST'])
@login_required
def create_project():
    uid  = session['user_id']
    name = (request.json.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    with get_db() as db:
        max_pos = db.execute(
            'SELECT COALESCE(MAX(position), 0) FROM task_groups WHERE owner_id = ?', (uid,)
        ).fetchone()[0]
        cur = db.execute(
            'INSERT INTO task_groups (owner_id, name, position) VALUES (?, ?, ?)',
            (uid, name, max_pos + 1)
        )
        db.commit()
        group = db.execute(
            'SELECT *, 0 as task_count FROM task_groups WHERE id = ?', (cur.lastrowid,)
        ).fetchone()
    return jsonify(dict(group)), 201

@app.route('/api/projects/<int:group_id>', methods=['PATCH'])
@login_required
def update_project(group_id):
    uid  = session['user_id']
    data = request.json
    sets, params = [], []
    if 'name' in data:
        sets.append('name = ?'); params.append(data['name'].strip())
    if 'position' in data:
        sets.append('position = ?'); params.append(data['position'])
    if not sets:
        return jsonify({'error': 'Nothing to update'}), 400
    params += [group_id, uid]
    with get_db() as db:
        db.execute(
            f'UPDATE task_groups SET {", ".join(sets)} WHERE id = ? AND owner_id = ?', params
        )
        db.commit()
        group = db.execute('SELECT * FROM task_groups WHERE id = ?', (group_id,)).fetchone()
    if not group:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(group))

@app.route('/api/projects/<int:group_id>', methods=['DELETE'])
@login_required
def delete_project(group_id):
    uid = session['user_id']
    with get_db() as db:
        group = db.execute(
            'SELECT * FROM task_groups WHERE id = ? AND owner_id = ?', (group_id, uid)
        ).fetchone()
        if not group:
            return jsonify({'error': 'Not found'}), 404
        # Move tasks to ungrouped instead of deleting them
        db.execute(
            'UPDATE tasks SET group_id = NULL WHERE group_id = ? AND owner_id = ?', (group_id, uid)
        )
        db.execute('DELETE FROM task_groups WHERE id = ? AND owner_id = ?', (group_id, uid))
        db.commit()
    return jsonify({'ok': True})

@app.route('/api/reorder', methods=['POST'])
@login_required
def reorder():
    uid  = session['user_id']
    data = request.json
    with get_db() as db:
        for t in data.get('tasks', []):
            db.execute(
                'UPDATE tasks SET group_id = ?, position = ? WHERE id = ? AND owner_id = ?',
                (t.get('group_id'), t['position'], t['id'], uid)
            )
        for g in data.get('groups', []):
            db.execute(
                'UPDATE task_groups SET position = ? WHERE id = ? AND owner_id = ?',
                (g['position'], g['id'], uid)
            )
        db.commit()
    return jsonify({'ok': True})

# ─────────────────────────────────────────────
# ADMIN ROUTES
# ─────────────────────────────────────────────

@app.route('/admin')
@login_required
@admin_required
def admin():
    with get_db() as db:
        users = db.execute('SELECT id, username, is_admin, active FROM users ORDER BY username').fetchall()
    return render_template('admin.html', users=users)

@app.route('/admin/create_user', methods=['POST'])
@login_required
@admin_required
def create_user():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    is_admin = 1 if request.form.get('is_admin') else 0
    if not username or not password:
        flash('Username and password are required.', 'error')
        return redirect(url_for('admin'))
    try:
        with get_db() as db:
            db.execute(
                'INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)',
                (username, generate_password_hash(password, method='pbkdf2:sha256'), is_admin)
            )
            db.commit()
        flash(f'User "{username}" created successfully.', 'success')
    except sqlite3.IntegrityError:
        flash(f'Username "{username}" already exists.', 'error')
    return redirect(url_for('admin'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == session['user_id']:
        flash("You can't delete yourself.", 'error')
        return redirect(url_for('admin'))
    with get_db() as db:
        db.execute('DELETE FROM tasks WHERE owner_id = ?', (user_id,))
        db.execute('DELETE FROM users WHERE id = ?', (user_id,))
        db.commit()
    flash('User deleted.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/toggle_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    if user_id == session['user_id']:
        flash("You can't disable your own account.", 'error')
        return redirect(url_for('admin'))
    with get_db() as db:
        user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('admin'))
        # Safety: don't allow disabling the last active admin
        if user['is_admin'] and user['active']:
            active_admins = db.execute(
                'SELECT COUNT(*) as c FROM users WHERE is_admin = 1 AND active = 1'
            ).fetchone()
            if active_admins['c'] <= 1:
                flash("Can't disable the last active admin account.", 'error')
                return redirect(url_for('admin'))
        new_status = 0 if user['active'] else 1
        db.execute('UPDATE users SET active = ? WHERE id = ?', (new_status, user_id))
        db.commit()
    action = 'disabled' if new_status == 0 else 're-enabled'
    flash(f'User "{user["username"]}" has been {action}.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/reset_password/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def reset_password(user_id):
    new_pw = request.form.get('new_password', '').strip()
    if not new_pw:
        flash('Password cannot be empty.', 'error')
        return redirect(url_for('admin'))
    with get_db() as db:
        db.execute('UPDATE users SET password = ? WHERE id = ?',
                   (generate_password_hash(new_pw, method='pbkdf2:sha256'), user_id))
        db.commit()
    flash('Password updated.', 'success')
    return redirect(url_for('admin'))

# ─────────────────────────────────────────────
# START
# ─────────────────────────────────────────────

if __name__ == '__main__':
    # ── Port resolution: CLI arg → config.json → default 8080 ──
    parser = argparse.ArgumentParser(description='PumaTracker')
    parser.add_argument('--port', type=int, default=None, help='Port to listen on (default: 8080)')
    args = parser.parse_args()

    port = args.port
    if port is None:
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        if os.path.exists(config_path):
            with open(config_path) as f:
                cfg = json.load(f)
            port = cfg.get('port', 8080)
        else:
            port = 8080

    init_db()
    print(f"🚀 PumaTracker running at http://localhost:{port}")
    app.run(debug=True, host='0.0.0.0', port=port)
