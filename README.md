# TaskMaster

A multi-user task manager with GTD support, built with Python and Flask.

---

## Setup (first time only)

### 1. Install Python
If you don't have Python installed, download it from https://python.org.
In WSL you can run: `sudo apt install python3 python3-pip`

### 2. Put the files somewhere
Create a folder, e.g. `~/taskmaster`, and put all these files in it:
```
taskmaster/
  app.py
  requirements.txt
  templates/
    login.html
    index.html
    admin.html
```

### 3. Install dependencies
Open a terminal in that folder and run:
```
pip install -r requirements.txt
```

### 4. Start the server
```
python app.py
```

You should see:
```
✅ Created default admin account: username=admin password=admin
🚀 TaskMaster running at http://localhost:5000
```

### 5. Open in your browser
Go to: http://localhost:5000

Log in with:
- Username: `admin`
- Password: `admin`

⚠️  **Change the admin password right away** via the Admin panel → Reset Password.

---

## Creating Users

1. Log in as admin
2. Click **Admin** in the top-right corner
3. Fill in the username and a temporary password, then click **Create User**
4. Share the credentials with each person — they can use the app at http://YOUR-IP:5000

To find your local IP (so others on your network can connect), run:
```
hostname -I
```

---

## Features

- ✅ Each user has their own task list
- ✅ Tasks have: GTD status, Status, Priority, Assignee note, Due date
- ✅ Send any task to another user's Inbox with the ↗ Send button
- ✅ Sidebar views and top-bar filters
- ✅ Admin panel to create/delete users and reset passwords
- ✅ Data saved in a local SQLite database file (taskmaster.db)

---

## Stopping the server
Press `Ctrl+C` in the terminal.

## Restarting
Just run `python app.py` again — your data is saved in `taskmaster.db`.
