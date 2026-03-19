"""PumaTracker server configuration."""

import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'pumatracker.db')

# Backups
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
BACKUP_INTERVAL_HOURS = 6
BACKUP_MAX_COUNT = 10

# Server
HOST = '0.0.0.0'
PORT = int(os.environ.get('PORT', 5001))


def _load_or_generate_secret():
    """Load secret key from file, or generate and persist a new one."""
    env_key = os.environ.get('PUMATRACKER_SECRET')
    if env_key:
        return env_key
    path = os.path.join(DATA_DIR, '.secret_key')
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, 'w') as f:
        f.write(key)
    return key


SECRET_KEY = _load_or_generate_secret()

# Sessions
SESSION_LIFETIME_DAYS = 30
