import sqlite3
from contextlib import closing
from multiprocessing import Pool

from job_queue import add_job, claim_next_job, finish_job


def read_rows(path):
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM jobs ORDER BY id")]


def test_add_job_writes_pending_record(tmp_path):
    queue = tmp_path / "queue.db"

    first = add_job(queue)
    second = add_job(queue)

    rows = read_rows(queue)
    assert [r["id"] for r in rows] == [first, second]
    assert all(r["status"] == "pending" for r in rows)


def test_claim_takes_oldest_pending_and_marks_in_progress(tmp_path):
    queue = tmp_path / "queue.db"
    add_job(queue)
    add_job(queue)

    job_id = claim_next_job(queue, consumer="c1")

    rows = read_rows(queue)
    assert job_id == 1
    assert rows[0]["status"] == "in_progress"
    assert rows[0]["consumer"] == "c1"
    assert rows[1]["status"] == "pending"


def test_claim_returns_none_when_nothing_pending(tmp_path):
    queue = tmp_path / "queue.db"
    assert claim_next_job(queue, consumer="c1") is None

    add_job(queue)
    claim_next_job(queue, consumer="c1")
    assert claim_next_job(queue, consumer="c1") is None


def test_finish_job_marks_done(tmp_path):
    queue = tmp_path / "queue.db"
    add_job(queue)
    job_id = claim_next_job(queue, consumer="c1")

    finish_job(queue, job_id)

    assert read_rows(queue)[0]["status"] == "done"


def _claim(path):
    return claim_next_job(path, consumer="worker")


def test_parallel_consumers_never_claim_the_same_job(tmp_path):
    queue = tmp_path / "queue.db"
    for _ in range(50):
        add_job(queue)

    with Pool(8) as pool:
        claimed = pool.map(_claim, [queue] * 60)

    job_ids = [j for j in claimed if j is not None]
    assert sorted(job_ids) == list(range(1, 51))
