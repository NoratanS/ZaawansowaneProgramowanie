"""Add one pending job (one phone call) to the queue."""

from job_queue import QUEUE_FILE, add_job

if __name__ == "__main__":
    job_id = add_job(QUEUE_FILE)
    print(f"Added job {job_id}")
