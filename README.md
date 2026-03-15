# PumaTracker

A single-user, offline-first task manager built on [GTD](https://gettingthingsdone.com/) principles. Runs entirely in the browser with no server, no account, and no internet connection required.

## Usage

Double-click `index.html` to open in your browser. That's it.

> Alternatively, serve it locally with `python3 -m http.server 8080` and open `http://localhost:8080`.

On first launch, a welcome screen explains the basics and reminds you to export your data regularly.

---

## Features

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
- **Checkbox** — click the circle to toggle done/undone (animated checkmark draw)
- **Pill selects** — change GTD, Status, and Priority directly in the row
- **Subtasks** — one level deep; add via right-click context menu
- **Recurrence** — daily, weekly, monthly, or yearly; spawns the next occurrence on completion
- **Due dates** — overdue dates highlighted in red
- **Assignee and URL** fields in the task detail panel
- **Notes** — timestamped log entries per task

### Projects
- Create, rename, and delete projects from the sidebar
- Drag to reorder projects
- Filter the task list to a single project by clicking it

### Filtering
- **Sidebar** — filter by GTD view, priority level, or project
- **Topbar dropdowns** — cross-filter by Priority, Status, and GTD simultaneously

### Data
- **Export ↓** — downloads a dated JSON backup of all tasks, projects, and notes
- **Import ↑** — restores data from a previously exported JSON file (replaces current data)
- **Archive ↓** — moves all completed tasks to the Archive view

---

## Keyboard Shortcuts

Press **`?`** anywhere in the app (when not typing) to open the shortcuts reference panel.

| Key | Action |
|-----|--------|
| `j` | Next task |
| `k` | Previous task |
| `↑` / `↓` | Navigate tasks |
| `Enter` | Open task detail panel |
| `e` | Rename focused task |
| `Esc` | Clear focus / close panel |
| `?` | Show keyboard shortcuts |

---

## Data Handling

All data is stored in your browser's **localStorage** under three keys:

| Key | Contents |
|-----|----------|
| `pumatracker.tasks` | All tasks and subtasks |
| `pumatracker.groups` | Projects |
| `pumatracker.notes` | Per-task notes |

### What this means
- **Data is local to your browser.** Opening `index.html` from a different browser, device, or file path will show an empty app.
- **Clearing browser data will erase your tasks.** Use Export regularly to back up your data.
- **Incognito/private mode does not persist data** across sessions.
- **The file itself contains no data.** The HTML file is just the app; your data lives separately in localStorage.

### Recommended workflow
1. Use **Export ↓** periodically to save a dated JSON backup.
2. To move to a new browser or device, Export on the old one and Import on the new one.
3. To reset to a clean state, Import a file with empty arrays or clear localStorage manually.

### Demo data
A `demo.json` file is included with sample tasks covering all GTD views, priorities, statuses, subtasks, and recurrence. To load it, open the browser console and run:

```js
fetch('demo.json').then(r=>r.json()).then(d=>{
  localStorage.setItem('pumatracker.tasks',  JSON.stringify(d.tasks));
  localStorage.setItem('pumatracker.groups', JSON.stringify(d.groups));
  localStorage.setItem('pumatracker.notes',  JSON.stringify(d.notes));
  location.reload();
});
```

> This requires the file to be served (e.g. via `python3 -m http.server`), not opened directly as `file://`.
