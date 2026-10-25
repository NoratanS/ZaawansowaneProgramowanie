import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import aio_pika
import pytest

pytestmark = pytest.mark.integration

IMAGE_URL = "https://images.example/people.jpg"


async def test_analysis_request_is_accepted_and_queued(client, drain):
    before = datetime.now(UTC)

    response = await client.post("/analyses", json={"image_url": IMAGE_URL})

    assert response.status_code == 202
    body = response.json()
    job_id = UUID(body["job_id"])
    assert body["result_url"] == f"http://results.example/results/{job_id}"
    assert response.headers["location"] == body["result_url"]

    [message] = await drain("analysis-jobs")
    assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    job = json.loads(message.body)
    assert job.keys() == {"job_id", "image_url", "requested_at"}
    assert job["job_id"] == str(job_id)
    assert job["image_url"] == IMAGE_URL
    requested_at = datetime.fromisoformat(job["requested_at"])
    assert requested_at.utcoffset() == timedelta(0)
    assert before <= requested_at <= datetime.now(UTC)


@pytest.mark.parametrize(
    "results_public_url",
    ["https://pc.example/results-app", "https://pc.example/results-app/"],
)
async def test_result_url_has_no_double_slash(client_for, results_public_url):
    async with client_for(results_public_url=results_public_url) as client:
        response = await client.post("/analyses", json={"image_url": IMAGE_URL})

    job_id = response.json()["job_id"]
    expected = f"https://pc.example/results-app/results/{job_id}"
    assert response.json()["result_url"] == expected
    assert response.headers["location"] == expected


async def test_same_image_twice_gets_two_jobs(client, drain):
    first = await client.post("/analyses", json={"image_url": IMAGE_URL})
    second = await client.post("/analyses", json={"image_url": IMAGE_URL})

    assert first.json()["job_id"] != second.json()["job_id"]
    queued = [json.loads(m.body)["job_id"] for m in await drain("analysis-jobs")]
    assert queued == [first.json()["job_id"], second.json()["job_id"]]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"image_url": None},
        {"image_url": "not a url"},
        {"image_url": "people.jpg"},
        {"image_url": "ftp://images.example/people.jpg"},
        {"image_url": "file:///etc/passwd"},
        {"image_url": "http://"},
    ],
    ids=["missing", "null", "malformed", "relative", "ftp", "file", "no-host"],
)
async def test_bad_image_url_is_rejected_and_nothing_is_queued(client, drain, body):
    response = await client.post("/analyses", json=body)

    assert response.status_code == 422
    assert await drain("analysis-jobs") == []


async def test_unroutable_publish_gives_503(client, channel):
    await channel.queue_delete("analysis-jobs")

    response = await client.post("/analyses", json={"image_url": IMAGE_URL})

    assert response.status_code == 503


async def test_publish_nacked_by_the_broker_gives_503(client, channel, drain):
    # Swap in a queue that refuses every message, so the broker nacks.
    await channel.queue_delete("analysis-jobs")
    await channel.declare_queue(
        "analysis-jobs",
        durable=True,
        arguments={"x-max-length": 0, "x-overflow": "reject-publish"},
    )

    response = await client.post("/analyses", json={"image_url": IMAGE_URL})

    assert response.status_code == 503
    assert await drain("analysis-jobs") == []


async def test_lost_broker_connection_gives_503(client, rabbitmq):
    rabbitmq.exec(["rabbitmqctl", "close_all_connections", "test"])
    # Let the client notice; it then waits several seconds to reconnect.
    await asyncio.sleep(0.5)

    response = await client.post("/analyses", json={"image_url": IMAGE_URL})

    assert response.status_code == 503
