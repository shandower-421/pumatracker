# PumaTracker

A multi-user GTD task manager built on [Getting Things Done](https://gettingthingsdone.com/) principles. Runs as a lightweight Python server on your local network so household members can share a common set of tasks from any browser.

## Prerequisites

- Python 3.9+
- pip

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python3 server.py
```

The server starts on `http://0.0.0.0:5001` by default. Open it from any device on your LAN at `http://<your-ip>:5001`.

On first launch you'll be prompted to create an admin account. The admin can then create accounts for other household members from the Admin tab.

### Configuration

| Environment variable | Default | Purpose |
|---------------------|---------|---------|
| `PORT` | `5001` | Server port |
| `PUMATRACKER_SECRET` | auto-generated | Session signing key (persisted to `data/.secret_key` if not set) |
| `FLASK_DEBUG` | off | Set to `1` for development mode |

### Demo Data

A `demo.json` file is included with sample tasks. To load it, use the **Import** button in the app's help menu (click **?** in the topbar).

---

## Features

### Multi-User

- Shared task data — all users see the same projects and tasks
- Per-user comments with author attribution
- Admin role for user management (first account is automatically admin)
- Session-based auth with HttpOnly cookies (30-day lifetime)

### Admin Panel

Accessible from the **?** menu (Admin tab, visible to admins only):

- **User management** — create, promote/demote, and remove users
- **Backups** — create, restore, and delete SQLite backups
- Automatic rotating backups every 6 hours (keeps last 10)

### GTD Views

Tasks are organized into seven GTD buckets, accessible from the sidebar:

| View | Purpose |
|------|---------|
| **Inbox** | Unprocessed captures |
| **Today** | Committed to today |
| **Soon** | On deck for the near future |
| **Waiting** | Blocked on someone else |
| **Someday** | Low-urgency ideas |
| **On Hold** | Paused pending external factors |
| **Archive** | Completed and archived tasks |

### Tasks
- Add tasks by typing in the input bar and pressing **Enter**
- **Inline rename** — click a task name to edit it in place
- **Checkbox** — click to toggle done/undone (animated checkmark)
- **Pill selects** — change GTD, Status, and Priority directly in the row
- **Subtasks** — one level deep; add via right-click context menu
- **Recurrence** — daily, weekly, monthly, or yearly; spawns the next occurrence on completion
- **Due dates** — overdue dates highlighted in red with pulsing indicator
- **Assignee and URL** fields in the task detail panel
- **Comments** — timestamped log entries per task with markdown support
- **Delete confirmation** — task deletion requires explicit confirmation

### Live Search
Type `/` in the add-task input to enter search mode. The task list live-filters as you type, matching against task names, descriptions, and assignees. Press **Escape** to clear the search and return to normal view.

### Markdown Descriptions
The task detail panel supports markdown in descriptions with an **Edit/Preview** toggle:
- Headings (`# H1`, `## H2`, `### H3`)
- **Bold** (`**text**`) and *italic* (`*text*`)
- Inline `code` and fenced code blocks (` ``` `)
- Bullet lists (`- item`)
- Blockquotes (`> quote`)
- [Links](`[text](url)`)
- Horizontal rules (`---`)

Comments also render markdown automatically.

### Projects
- Create, rename, and delete projects from the sidebar
- Drag to reorder projects
- Filter the task list to a single project by clicking it

### Filtering
- **Sidebar** — filter by GTD view, priority level, or project
- **Topbar dropdowns** — cross-filter by Priority, Status, and GTD simultaneously
- **Search** — type `/query` in the input bar for instant text search

### Dark / Light Theme
Click the **sun/moon toggle** in the topbar to switch between dark and light themes. Your preference persists across sessions.

### Data Management
- **Export** — downloads a dated JSON backup of all tasks, projects, and comments
- **Import** — restores data from a previously exported JSON file (with confirmation prompt)
- **Archive** — moves all completed tasks to the Archive view
- **Password change** — each user can change their own password from the Your Data tab

---

## Keyboard Shortcuts

Press **`?`** anywhere in the app (when not typing) to open the shortcuts reference panel.

| Key | Action |
|-----|--------|
| `j` / `↓` | Next task |
| `k` / `↑` | Previous task |
| `Enter` | Open task detail panel |
| `e` | Rename focused task |
| `Esc` | Clear focus / close panel / clear search |
| `Cmd/Ctrl+S` | Save task panel |
| `/` | Search tasks (type in add-task input) |
| `?` | Show keyboard shortcuts |

---

## Accessibility

- Semantic HTML with `<main>`, `<nav>`, proper heading hierarchy
- ARIA roles and labels on all interactive elements (checkboxes, selects, dialogs, menus)
- Focus trapping in modals and panels
- Keyboard-navigable throughout (tab, arrow keys, Enter, Escape)
- Focus-visible indicators on all interactive elements
- Skip-to-content link
- `prefers-reduced-motion` respected — all animations disabled
- Contrast ratios meet WCAG AA (4.5:1+)
- Touch targets sized for mobile (32px+ checkboxes, 36px+ buttons)

---

## Responsive Design

| Breakpoint | Behavior |
|------------|----------|
| **Desktop** (1024px+) | Full sidebar, all 8 table columns, filter dropdowns |
| **Tablet** (768–1023px) | Narrower sidebar, assignee column hidden |
| **Mobile** (360–767px) | Off-canvas sidebar drawer, status/project/assignee/due columns hidden |
| **Small mobile** (<360px) | GTD and priority columns also hidden, compact topbar |

---

## Data Storage

All data is stored in a SQLite database at `data/pumatracker.db`. The `data/` directory is gitignored and contains:

| Path | Contents |
|------|----------|
| `data/pumatracker.db` | SQLite database (tasks, projects, comments, users, sessions) |
| `data/backups/` | Rotating SQLite backup files |
| `data/.secret_key` | Auto-generated session signing key |

### Backups

- Automatic backup on server startup
- Scheduled backups every 6 hours (configurable in `config.py`)
- Keeps the 10 most recent backups (oldest are rotated out)
- Admins can create, restore, and delete backups from the Admin tab
- Restoring a backup creates a safety backup first

---

## Security

- **Session auth** — HttpOnly, SameSite=Lax cookies; no tokens in localStorage
- **Password hashing** — werkzeug pbkdf2:sha256
- **Import sanitization** — field whitelists, type coercion, and length limits
- **Path traversal prevention** — backup filenames validated and realpath-checked
- **XSS protection** — all user content is HTML-escaped before rendering
- **No hardcoded secrets** — session key auto-generated and persisted to disk
- **Session cleanup** — expired sessions pruned on each request
- **Session invalidation** — admin password resets invalidate all user sessions

## License

MIT
