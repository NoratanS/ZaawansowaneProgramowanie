"""A job queue stored in a SQLite database, shared by producers and consumers.

SQLite does the locking for us. Claiming a job is one ``UPDATE ... RETURNING``
statement, and SQLite runs each statement as an atomic transaction, so two
consumers can never both take the same ``pending`` job.
"""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

QUEUE_DB = Path(__file__).parent / "queue.db"

PENDING = "pending"
IN_PROGRESS = "in_progress"
DONE = "done"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    status     TEXT NOT NULL,
    consumer   TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def connect(path):
    # autocommit=True: every statement commits on its own, no forgotten commit().
    # timeout: wait up to 30s for another process's write lock instead of failing.
    conn = sqlite3.connect(path, timeout=30, autocommit=True)
    conn.execute(SCHEMA)
    return conn


def add_job(path=QUEUE_DB):
    now = _now()
    with closing(connect(path)) as conn:
        cur = conn.execute(
            "INSERT INTO jobs (status, created_at, updated_at) VALUES (?, ?, ?)",
            (PENDING, now, now),
        )
        return cur.lastrowid


def claim_next_job(path=QUEUE_DB, consumer=""):
    """Mark the oldest pending job as in_progress and return its id."""
    with closing(connect(path)) as conn:
        row = conn.execute(
            """
            UPDATE jobs SET status = ?, consumer = ?, updated_at = ?
            WHERE id = (
                SELECT id FROM jobs WHERE status = ? ORDER BY id LIMIT 1
            )
            RETURNING id
            """,
            (IN_PROGRESS, consumer, _now(), PENDING),
        ).fetchone()
    return row[0] if row else None


def finish_job(path, job_id):
    with closing(connect(path)) as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
            (DONE, _now(), job_id),
        )


def _now():
    return datetime.now().isoformat(timespec="seconds")
