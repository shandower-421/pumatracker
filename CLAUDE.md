# CLAUDE.md — PumaTracker

## Project Overview

PumaTracker is a multi-user, GTD-based task manager web app. Single Python file backend (`app.py`) with vanilla JS/HTML/CSS frontend (no build step).

## Tech Stack

- **Backend:** Python 3, Flask, SQLite, Werkzeug
- **Frontend:** Vanilla JS (ES6), HTML5, CSS3 (CSS custom properties), no frameworks or bundlers
- **Templates:** Jinja2 (`templates/`)

## Running the Project

```bash
pip install -r requirements.txt
python app.py               # starts at http://localhost:8080
python app.py --port 9000   # custom port
python app.py --debug       # auto-reload dev mode
```

Default credentials: `admin` / `admin`

Port can also be set in `config.json`.

## Key Files

| File | Purpose |
|------|---------|
| `app.py` | Entire backend: Flask routes, DB schema, auth, API |
| `templates/index.html` | Main app UI (HTML + embedded CSS + embedded JS, ~1800 lines) |
| `templates/login.html` | Login page |
| `templates/admin.html` | Admin user management |
| `config.json` | Port and secret_key (auto-generated if missing) |
| `requirements.txt` | `flask`, `werkzeug` |

## Database

- SQLite, file: `pumatracker.db` (gitignored, auto-created on first run)
- 3 tables: `users`, `task_groups`, `tasks`
- Use `get_db()` context manager for all DB access
- Parameterized queries throughout — never format SQL with string interpolation
- Schema migrations use `try/except` on `ALTER TABLE`

## Architecture Patterns

**Backend (app.py):**
- `login_required` and `admin_required` decorators protect routes
- All task/project queries filter by `owner_id` for user isolation
- `done` flag auto-syncs with status field
- CSRF token validated on all state-changing requests
- Passwords hashed with `pbkdf2:sha256` via Werkzeug

**Frontend (index.html):**
- Fetch API for all AJAX; no jQuery or axios
- CSS variables (`--color-*`, `--space-*`) for theming; supports light and dark mode
- Native HTML5 drag-and-drop for task/subtask reordering
- Toast notifications for user feedback
- Right-click context menus (disabled when task detail panel is open)

## GTD Model

- **GTD columns:** Inbox, Today, Soon, Waiting, Someday, On Hold
- **Priorities:** CRIT, High, Medium, Low, Info
- **Status:** Not Started, In Progress, Completed (syncs `done` flag)
- Subtasks supported with parent/child relationships and expand/collapse

## API Endpoints

All return JSON. Require session auth.

| Method | Path | Purpose |
|--------|------|---------|
| GET/POST | `/api/tasks` | List / create tasks |
| PATCH/DELETE | `/api/tasks/<id>` | Update / delete task |
| POST | `/api/tasks/<id>/assign` | Delegate task to another user |
| GET/POST | `/api/projects` | List / create projects |
| PATCH/DELETE | `/api/projects/<id>` | Update / delete project |
| GET | `/api/counts` | Task statistics |
| POST | `/api/archive` | Archive completed tasks |
| POST | `/api/reorder` | Bulk reorder tasks or projects |

## Common Tasks

**Add a new API endpoint:** Add route in `app.py`, handle JSON in/out, filter by `session['user_id']`, validate CSRF token for mutations.

**Add a new DB column:** Add `ALTER TABLE` migration in `init_db()` wrapped in `try/except`.

**Add a new frontend feature:** Edit `templates/index.html` — CSS is in the `<style>` block, JS is in the `<script>` block at the bottom.

## No Test Suite

There are no automated tests. Test changes manually in the browser.
