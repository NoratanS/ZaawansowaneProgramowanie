"""Take jobs from the queue, count the people and save the annotated image.

Start as many copies as you need: RabbitMQ hands each job to one consumer.
"""

import json
import os
from pathlib import PurePosixPath
from urllib.parse import urlparse

import cv2

from detector import detect_people, download_image
from rabbit import QUEUE, RESULTS_DIR, connect


def save_result(job_id: str, url: str, image, boxes) -> str:
    for x, y, width, height in boxes:
        cv2.rectangle(image, (x, y), (x + width, y + height), (0, 255, 0), 2)
    extension = PurePosixPath(urlparse(url).path).suffix.lower()
    if not cv2.haveImageWriter(f"x{extension}"):
        extension = ".jpg"
    name = f"{job_id}-{len(boxes)}{extension}"
    cv2.imwrite(str(RESULTS_DIR / name), image)
    return name


def main():
    name = f"consumer-{os.getpid()}"
    RESULTS_DIR.mkdir(exist_ok=True)

    def handle(channel, method, properties, body):
        job = json.loads(body)
        print(f"{name}: analysing {job['id']}")
        try:
            image = download_image(job["url"])
            saved = save_result(job["id"], job["url"], image, detect_people(image))
            print(f"{name}: saved {saved}")
        except (OSError, ValueError) as error:
            # A bad URL would fail again on retry, so drop the job.
            print(f"{name}: job {job['id']} failed: {error}")
        channel.basic_ack(delivery_tag=method.delivery_tag)

    connection, channel = connect()
    # Take one job at a time, so a busy consumer doesn't hoard the queue.
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE, on_message_callback=handle)
    print(f"{name} started")
    channel.start_consuming()


if __name__ == "__main__":
    main()
