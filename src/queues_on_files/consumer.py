"""Poll the queue forever and work through pending jobs one at a time."""

import os
import time

from job_queue import QUEUE_FILE, claim_next_job, finish_job

POLL_INTERVAL = 5  # seconds between checks when the queue is empty
JOB_DURATION = 30  # seconds one job takes


def main():
    name = f"consumer-{os.getpid()}"
    print(f"{name} started")
    while True:
        job_id = claim_next_job(QUEUE_FILE, consumer=name)
        if job_id is None:
            time.sleep(POLL_INTERVAL)
            continue
        print(f"{name}: working on job {job_id}")
        time.sleep(JOB_DURATION)
        finish_job(QUEUE_FILE, job_id)
        print(f"{name}: job {job_id} done")


if __name__ == "__main__":
    main()
