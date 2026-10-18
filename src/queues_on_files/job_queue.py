"""A job queue stored in a CSV file, shared by producers and consumers.

Every read-modify-write happens while holding an exclusive lock on a
separate ``.lock`` file. Without it, two consumers could both read the
same ``pending`` job before either saves ``in_progress``, and both would
take it.
"""

import csv
import fcntl
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

QUEUE_FILE = Path(__file__).parent / "queue.csv"
FIELDS = ["id", "status", "consumer", "created_at", "updated_at"]

PENDING = "pending"
IN_PROGRESS = "in_progress"
DONE = "done"


@contextmanager
def locked_rows(path):
    """Yield the queue rows as a list; changes are saved on exit."""
    path = Path(path)
    with open(path.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = _read(path)
        yield rows
        _write(path, rows)


def add_job(path=QUEUE_FILE):
    with locked_rows(path) as rows:
        job_id = max((int(r["id"]) for r in rows), default=0) + 1
        now = _now()
        rows.append(
            {
                "id": job_id,
                "status": PENDING,
                "consumer": "",
                "created_at": now,
                "updated_at": now,
            }
        )
    return job_id


def claim_next_job(path=QUEUE_FILE, consumer=""):
    """Mark the oldest pending job as in_progress and return its id."""
    with locked_rows(path) as rows:
        for row in rows:
            if row["status"] == PENDING:
                row["status"] = IN_PROGRESS
                row["consumer"] = consumer
                row["updated_at"] = _now()
                return int(row["id"])
    return None


def finish_job(path, job_id):
    with locked_rows(path) as rows:
        for row in rows:
            if int(row["id"]) == job_id:
                row["status"] = DONE
                row["updated_at"] = _now()


def _read(path):
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _write(path, rows):
    # Write to a temp file and swap it in, so a crash mid-write
    # never leaves a half-written queue behind.
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def _now():
    return datetime.now().isoformat(timespec="seconds")
