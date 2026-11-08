import asyncio
from contextlib import asynccontextmanager

import aio_pika
import httpx
import pytest
from aiobotocore.session import get_session
from botocore.config import Config
from botocore.exceptions import ClientError

from analysis_service.api import create_app
from analysis_service.queues import JOBS_QUEUE, RESULTS_QUEUE
from analysis_service.settings import AnalysisApiSettings
from analysis_service.uploads import UPLOADS_BUCKET

ANALYSIS_PUBLIC_URL = "http://analysis.example"


@pytest.fixture
async def channel(rabbitmq_url):
    """A raw AMQP channel for inspecting and tampering with the broker."""
    async with await aio_pika.connect(rabbitmq_url) as connection:
        yield await connection.channel()


@pytest.fixture
async def clean_broker(channel):
    """Delete every queue topology so each test's app declares it afresh."""
    for name in (JOBS_QUEUE, RESULTS_QUEUE):
        await channel.queue_delete(name)
        await channel.queue_delete(f"{name}.dlq")
        await channel.exchange_delete(f"{name}.dlx")


@pytest.fixture
async def s3_client(s3):
    """A raw S3 client for inspecting and seeding the upload store."""
    session = get_session()
    async with session.create_client(
        "s3",
        endpoint_url=s3.endpoint_url,
        aws_access_key_id=s3.access_key,
        aws_secret_access_key=s3.secret_key,
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    ) as client:
        yield client


@pytest.fixture
async def upload_settings(s3, s3_client):
    """Store settings for an app, with the bucket gone so the app creates it."""
    try:
        listing = await s3_client.list_objects_v2(Bucket=UPLOADS_BUCKET)
    except ClientError:
        pass  # no bucket yet
    else:
        for item in listing.get("Contents", []):
            await s3_client.delete_object(Bucket=UPLOADS_BUCKET, Key=item["Key"])
        await s3_client.delete_bucket(Bucket=UPLOADS_BUCKET)
    return {
        "s3_endpoint_url": s3.endpoint_url,
        "s3_access_key": s3.access_key,
        "s3_secret_key": s3.secret_key,
        "analysis_public_url": ANALYSIS_PUBLIC_URL,
    }


@pytest.fixture
async def stored_keys(s3_client):
    """The keys currently in the upload bucket."""

    async def keys():
        listing = await s3_client.list_objects_v2(Bucket=UPLOADS_BUCKET)
        return [item["Key"] for item in listing.get("Contents", [])]

    return keys


@pytest.fixture
def client_for(rabbitmq_url, clean_broker, upload_settings, jwt_keys, mint_token):
    """Open an Analysis Service client with its lifespan running.

    The client sends a valid client token unless ``authorized`` is false.
    """

    @asynccontextmanager
    async def open_client(results_public_url="http://results.example", authorized=True):
        settings = AnalysisApiSettings(
            rabbitmq_url=rabbitmq_url,
            results_public_url=results_public_url,
            jwt_public_key=jwt_keys.public,
            **upload_settings,
        )
        headers = {}
        if authorized:
            headers["Authorization"] = f"Bearer {mint_token('analysis-service')}"
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://analysis", headers=headers
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


@pytest.fixture
async def anonymous_client(client_for):
    async with client_for(authorized=False) as client:
        yield client
