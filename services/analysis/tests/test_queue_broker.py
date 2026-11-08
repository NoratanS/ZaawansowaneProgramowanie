"""The queue module against a real broker: what each handler outcome does."""

import asyncio
import logging
from contextlib import asynccontextmanager

import pytest
from aiormq.exceptions import AMQPError

from analysis_service.queues import (
    JOBS_QUEUE,
    Action,
    NotQueued,
    Queue,
    QueueConfig,
    confirming_broker,
)

pytestmark = pytest.mark.integration

BODY = b'{"job_id": "1"}'


class ScriptedHandler:
    """Answers with ``actions`` in order, then ``ACK``; records each call."""

    def __init__(self, *actions):
        self.actions = list(actions)
        self.calls = []

    async def __call__(self, body, headers, message_id):
        self.calls.append((body, headers, message_id))
        action = self.actions.pop(0) if self.actions else Action.ACK
        if isinstance(action, Exception):
            raise action
        return action


@pytest.fixture
def queue_for(rabbitmq_url, clean_broker):
    """A declared jobs queue with fast retries, consumed by ``handler`` if given."""

    @asynccontextmanager
    async def open_queue(handler=None, delivery_limit=3):
        broker = confirming_broker(rabbitmq_url)
        queue = Queue(
            broker,
            QueueConfig(
                name=JOBS_QUEUE,
                retry_min_seconds=0.05,
                retry_max_seconds=0.2,
                delivery_limit=delivery_limit,
            ),
        )
        if handler is not None:
            queue.consume(handler, prefetch=1)
        await broker.connect()
        await queue.declare()
        await broker.start()
        try:
            yield queue
        finally:
            await broker.stop()

    return open_queue


async def wait_for_calls(handler, count, timeout=5):
    async with asyncio.timeout(timeout):
        while len(handler.calls) < count:
            await asyncio.sleep(0.02)


async def test_an_acked_message_leaves_the_queue(queue_for, drain):
    handler = ScriptedHandler(Action.ACK)

    async with queue_for(handler) as queue:
        await queue.publish(BODY, message_id="1")
        await wait_for_calls(handler, 1)
        # Give a stray redelivery the chance to show up.
        await asyncio.sleep(0.3)

    [(body, headers, message_id)] = handler.calls
    assert body == BODY
    assert isinstance(headers, dict)
    assert message_id == "1"
    assert await drain(JOBS_QUEUE) == []
    assert await drain(f"{JOBS_QUEUE}.dlq") == []


async def test_a_retried_message_is_delivered_again(queue_for, drain):
    handler = ScriptedHandler(Action.RETRY, Action.ACK)

    async with queue_for(handler) as queue:
        await queue.publish(BODY, message_id="1")
        await wait_for_calls(handler, 2)
        await asyncio.sleep(0.3)

    assert [body for body, *_ in handler.calls] == [BODY, BODY]
    # The Courier logs this header, so a redelivery must carry it.
    assert handler.calls[1][1]["x-delivery-count"] == 1
    assert await drain(JOBS_QUEUE) == []
    assert await drain(f"{JOBS_QUEUE}.dlq") == []


async def test_a_dead_lettered_message_goes_straight_to_the_dlq(
    queue_for, next_message, drain
):
    handler = ScriptedHandler(Action.DEAD_LETTER)

    async with queue_for(handler) as queue:
        await queue.publish(BODY, message_id="1")
        dead = await next_message(f"{JOBS_QUEUE}.dlq")
        await asyncio.sleep(0.3)

    assert dead.body == BODY
    assert len(handler.calls) == 1
    assert await drain(JOBS_QUEUE) == []


async def test_a_raising_handler_is_retried_then_dead_lettered(
    queue_for, next_message, drain, caplog
):
    caplog.set_level(logging.ERROR, logger="analysis_service.queues")
    handler = ScriptedHandler(*[RuntimeError("handler exploded")] * 10)

    async with queue_for(handler, delivery_limit=2) as queue:
        await queue.publish(BODY, message_id="m-1")
        dead = await next_message(f"{JOBS_QUEUE}.dlq")
        await asyncio.sleep(0.3)

    assert dead.body == BODY
    # Tried once, then retried up to the delivery limit.
    assert len(handler.calls) == 1 + 2
    assert await drain(JOBS_QUEUE) == []
    errors = [r for r in caplog.records if r.name == "analysis_service.queues"]
    assert [r.getMessage() for r in errors] == [
        "message_id=m-1 requeued after an error"
    ] * 3
    assert all(r.exc_info for r in errors)


async def test_publishing_to_a_missing_queue_raises_not_queued(queue_for, channel):
    async with queue_for() as queue:
        await channel.queue_delete(JOBS_QUEUE)

        with pytest.raises(NotQueued) as raised:
            await queue.publish(BODY, message_id="1")

    assert isinstance(raised.value.__cause__, AMQPError)
