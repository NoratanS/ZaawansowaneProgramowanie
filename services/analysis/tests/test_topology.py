import asyncio

import pytest

from analysis_service.queues import JOBS_QUEUE

pytestmark = pytest.mark.integration

IMAGE_URL = "https://images.example/people.jpg"


async def test_rejected_job_is_dead_lettered_to_the_dlq(client, channel, drain):
    await client.post("/analyses", json={"image_url": IMAGE_URL})
    queue = await channel.get_queue(JOBS_QUEUE)

    message = await queue.get(no_ack=False)
    await message.reject(requeue=False)

    # The broker dead-letters asynchronously, so give it a moment.
    async with asyncio.timeout(5):
        while not (dead_letters := await drain(f"{JOBS_QUEUE}.dlq")):
            await asyncio.sleep(0.05)
    [dead] = dead_letters
    assert dead.body == message.body


async def test_restarted_api_accepts_the_existing_topology(client_for, drain):
    async with client_for() as client:
        await client.post("/analyses", json={"image_url": IMAGE_URL})

    async with client_for() as client:
        response = await client.post("/analyses", json={"image_url": IMAGE_URL})

    assert response.status_code == 202
    assert len(await drain(JOBS_QUEUE)) == 2
