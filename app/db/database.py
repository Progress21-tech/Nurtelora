import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app.config import get_settings

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, sender_hash TEXT UNIQUE NOT NULL, consent_status TEXT NOT NULL DEFAULT 'unknown',
 preferred_language TEXT, registration_state TEXT NOT NULL DEFAULT 'new', facility_id TEXT,
 reminder_opt_in INTEGER NOT NULL DEFAULT 0, stopped INTEGER NOT NULL DEFAULT 0,
 pending_appointment_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS consent_records (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), consent_type TEXT NOT NULL,
 status TEXT NOT NULL, notice_version TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS facilities (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, address TEXT NOT NULL, state TEXT, lga TEXT,
 latitude REAL, longitude REAL, phone TEXT, services TEXT NOT NULL DEFAULT '[]', opening_hours TEXT,
 source TEXT NOT NULL, last_verified_at TEXT, owner TEXT, verification_status TEXT NOT NULL DEFAULT 'unverified'
);
CREATE TABLE IF NOT EXISTS appointments (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), facility_id TEXT REFERENCES facilities(id),
 scheduled_at TEXT, source TEXT NOT NULL, confirmation_status TEXT NOT NULL,
 owner TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS knowledge_entries (
 id TEXT PRIMARY KEY, topic TEXT NOT NULL, intent TEXT NOT NULL, language TEXT NOT NULL, approved_text TEXT NOT NULL,
 source_title TEXT NOT NULL, source_url TEXT NOT NULL, reviewed_at TEXT, reviewer_role TEXT,
 version TEXT NOT NULL, review_due_at TEXT, review_status TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS processed_messages (
 message_id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), message_type TEXT NOT NULL,
 processing_status TEXT NOT NULL, error_category TEXT, outbound_message_id TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS interaction_events (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL, task_type TEXT NOT NULL, language TEXT,
 succeeded INTEGER NOT NULL, failure_category TEXT, latency_ms INTEGER,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

def _path() -> str:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        raise RuntimeError("This prototype currently supports SQLite only")
    return url.removeprefix("sqlite:///")

@contextmanager
def connection():
    path = _path()
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True) if Path(path).parent != Path('.') else None
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db() -> None:
    with connection() as conn:
        conn.executescript(SCHEMA)
        # Lightweight additive migrations keep existing local prototype databases usable.
        columns={row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "pending_appointment_at" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN pending_appointment_at TEXT")
        knowledge_columns={row[1] for row in conn.execute("PRAGMA table_info(knowledge_entries)").fetchall()}
        if "review_due_at" not in knowledge_columns:
            conn.execute("ALTER TABLE knowledge_entries ADD COLUMN review_due_at TEXT")

if __name__ == "__main__":
    init_db()
    print("Database initialized")
