import asyncio
from contextlib import asynccontextmanager

import aio_pika
import httpx
import pytest

from analysis_service.api import create_app
from analysis_service.settings import AnalysisApiSettings, WorkerSettings


@pytest.fixture
async def channel(rabbitmq_url):
    """A raw AMQP channel for inspecting and tampering with the broker."""
    async with await aio_pika.connect(rabbitmq_url) as connection:
        yield await connection.channel()


@pytest.fixture
async def clean_broker(channel, rabbitmq_url):
    """Delete every queue topology so each test's app declares it afresh."""
    settings = WorkerSettings(rabbitmq_url=rabbitmq_url)
    for config in (settings.jobs_queue, settings.results_queue):
        await channel.queue_delete(config.name)
        await channel.queue_delete(config.dlq)
        await channel.exchange_delete(config.dlx)


@pytest.fixture
def client_for(rabbitmq_url, clean_broker):
    """Open an Analysis Service client with its lifespan running."""

    @asynccontextmanager
    async def open_client(results_public_url="http://results.example"):
        settings = AnalysisApiSettings(
            rabbitmq_url=rabbitmq_url, results_public_url=results_public_url
        )
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://analysis"
            ) as client:
                yield client

    return open_client


@pytest.fixture
async def client(client_for):
    async with client_for() as client:
        yield client


@pytest.fixture
def drain(channel):
    """Take every message currently in a queue."""

    async def take_all(queue_name):
        queue = await channel.get_queue(queue_name)
        messages = []
        while (message := await queue.get(no_ack=True, fail=False)) is not None:
            messages.append(message)
        return messages

    return take_all


@pytest.fixture
def next_message(channel):
    """Wait for the next message on a queue and take it."""

    async def take(queue_name, timeout=5):
        queue = await channel.get_queue(queue_name)
        async with asyncio.timeout(timeout):
            while (message := await queue.get(no_ack=True, fail=False)) is None:
                await asyncio.sleep(0.02)
        return message

    return take
