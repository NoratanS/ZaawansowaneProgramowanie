"""Settings shared by the producer (API) and the consumers."""

import os
from pathlib import Path

import pika

RABBIT_HOST = os.environ.get("RABBIT_HOST", "localhost")
QUEUE = "images_to_analyze"
RESULTS_DIR = Path(__file__).parent / "results"


def connect() -> tuple[pika.BlockingConnection, pika.channel.Channel]:
    connection = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
    channel = connection.channel()
    # durable: the queue survives a RabbitMQ restart
    channel.queue_declare(queue=QUEUE, durable=True)
    return connection, channel
