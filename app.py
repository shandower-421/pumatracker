"""
TaskMaster - Flask Web App
Run with: python app.py
Then open http://localhost:5000 in your browser.
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, functools
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'change-this-to-a-random-string-in-production'

DB = 'taskmaster.db'

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
                is_admin INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id    INTEGER NOT NULL,
                name        TEXT NOT NULL,
                status      TEXT DEFAULT "To Do",
                priority    TEXT DEFAULT "Medium",
                gtd         TEXT DEFAULT "Inbox",
                assignee_id INTEGER,
                due         TEXT DEFAULT "",
                done        INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime("now")),
                FOREIGN KEY (owner_id)    REFERENCES users(id),
                FOREIGN KEY (assignee_id) REFERENCES users(id)
            );
        ''')

        # Create default admin if no users exist
        row = db.execute('SELECT COUNT(*) as c FROM users').fetchone()
        if row['c'] == 0:
            db.execute(
                'INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)',
                ('admin', generate_password_hash('admin'))
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
        users = db.execute('SELECT id, username FROM users ORDER BY username').fetchall()
    return render_template('index.html', users=users)

# ─────────────────────────────────────────────
# TASK API (JSON endpoints)
# ─────────────────────────────────────────────

@app.route('/api/tasks')
@login_required
def get_tasks():
    view     = request.args.get('view', 'all')
    f_prio   = request.args.get('priority', '')
    f_status = request.args.get('status', '')
    f_gtd    = request.args.get('gtd', '')
    uid      = session['user_id']

    query  = 'SELECT t.*, u.username as assignee_name FROM tasks t LEFT JOIN users u ON t.assignee_id = u.id WHERE t.owner_id = ?'
    params = [uid]

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

    query += ' ORDER BY t.created_at DESC'

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
            'INSERT INTO tasks (owner_id, name) VALUES (?, ?)',
            (session['user_id'], name)
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
    fields = ['name', 'status', 'priority', 'gtd', 'assignee_id', 'due', 'done']
    sets, params = [], []

    for f in fields:
        if f in data:
            sets.append(f'{f} = ?')
            params.append(data[f])

    # Auto-sync done flag with status
    if 'status' in data:
        sets.append('done = ?')
        params.append(1 if data['status'] == 'Done' else 0)

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
                COUNT(*) as all_tasks,
                SUM(gtd="Today")   as today,
                SUM(gtd="Inbox")   as inbox,
                SUM(gtd="Soon")    as soon,
                SUM(gtd="Waiting") as waiting,
                SUM(gtd="On Hold") as hold,
                SUM(priority="High")   as high,
                SUM(priority="Medium") as medium,
                SUM(priority="Low")    as low
               FROM tasks WHERE owner_id = ?''',
            (uid,)
        ).fetchone()
    return jsonify(dict(rows))

# ─────────────────────────────────────────────
# ADMIN ROUTES
# ─────────────────────────────────────────────

@app.route('/admin')
@login_required
@admin_required
def admin():
    with get_db() as db:
        users = db.execute('SELECT id, username, is_admin FROM users ORDER BY username').fetchall()
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
                (username, generate_password_hash(password), is_admin)
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
                   (generate_password_hash(new_pw), user_id))
        db.commit()
    flash('Password updated.', 'success')
    return redirect(url_for('admin'))

# ─────────────────────────────────────────────
# START
# ─────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    print("🚀 TaskMaster running at http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
