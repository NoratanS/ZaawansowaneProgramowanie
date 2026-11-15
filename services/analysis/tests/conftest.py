import asyncio
import logging
from contextlib import asynccontextmanager

import aio_pika
import httpx
import pytest
from aiobotocore.session import get_session
from botocore.config import Config
from botocore.exceptions import ClientError

from analysis_service.api.main import create_app
from analysis_service.queues import JOBS_QUEUE, RESULTS_QUEUE
from analysis_service.settings import AnalysisApiSettings
from analysis_service.uploads import UPLOADS_BUCKET
from fakes import FakeJobs, MemoryUploadStore

ANALYSIS_PUBLIC_URL = "http://analysis.example"


@pytest.fixture
def settings_env(monkeypatch, jwt_keys):
    """Isolate a settings class from the real env; return ``monkeypatch``.

    Every env var the class reads is cleared, then its required ones are set,
    so a developer's own env can't leak into the defaults.
    """
    required = {
        "rabbitmq_url": "amqp://guest:guest@rabbitmq:5672/",
        "s3_access_key": "access",
        "s3_secret_key": "secret",
        "jwt_public_key": jwt_keys.public,
        "jwt_private_key": jwt_keys.private,
    }

    def isolate(settings_class):
        for name, field in settings_class.model_fields.items():
            monkeypatch.delenv(name.upper(), raising=False)
            if field.is_required():
                monkeypatch.setenv(name.upper(), required[name])
        return monkeypatch

    return isolate


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


def _open_client(app, mint_token, authorized):
    """An httpx client on ``app``, with a valid client token if ``authorized``."""
    headers = {}
    if authorized:
        headers["Authorization"] = f"Bearer {mint_token('analysis-service')}"
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://analysis",
        headers=headers,
    )


@pytest.fixture
def client_for(rabbitmq_url, clean_broker, upload_settings, jwt_keys, mint_token):
    """Open an Analysis Service client with its lifespan running.

    It runs against the real RabbitMQ and S3 adapters, for integration tests.
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
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with _open_client(app, mint_token, authorized) as client:
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


@pytest.fixture
def fake_jobs():
    return FakeJobs()


@pytest.fixture
def fake_store():
    return MemoryUploadStore()


@pytest.fixture
def unit_client_for(fake_jobs, fake_store, jwt_keys, mint_token):
    """Like ``client_for``, but on the in-memory adapters: no containers."""

    @asynccontextmanager
    async def open_client(results_public_url="http://results.example", authorized=True):
        # Nothing connects to these: the injected adapters replace them.
        settings = AnalysisApiSettings(
            rabbitmq_url="amqp://unused/",
            results_public_url=results_public_url,
            jwt_public_key=jwt_keys.public,
            s3_endpoint_url="http://unused",
            s3_access_key="unused",
            s3_secret_key="unused",
            analysis_public_url=ANALYSIS_PUBLIC_URL,
        )
        app = create_app(settings, jobs=fake_jobs, store=fake_store)
        async with app.router.lifespan_context(app):
            async with _open_client(app, mint_token, authorized) as client:
                yield client

    return open_client


@pytest.fixture
async def unit_client(unit_client_for):
    async with unit_client_for() as client:
        yield client


@pytest.fixture
async def unit_anonymous_client(unit_client_for):
    async with unit_client_for(authorized=False) as client:
        yield client


@pytest.fixture
def courier_logs(caplog):
    caplog.set_level(logging.INFO, logger="analysis_service.courier.deliver")

    def lines(level):
        return [
            r.getMessage()
            for r in caplog.records
            if r.name == "analysis_service.courier.deliver" and r.levelno == level
        ]

    return lines
