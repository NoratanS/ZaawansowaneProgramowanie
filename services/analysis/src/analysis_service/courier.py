"""Courier: delivers Analysis Results to the Results Service.

Run with ``python -m analysis_service.courier``.
"""

import asyncio
import json
import logging
from enum import Enum
from uuid import UUID

import httpx
from faststream import AckPolicy, FastStream
from faststream.rabbit import QueueType, RabbitBroker, RabbitQueue
from faststream.rabbit.annotations import RabbitMessage
from faststream.rabbit.schemas import Channel

from analysis_service.auth import CourierToken
from analysis_service.queues import declare_queue
from analysis_service.settings import CourierSettings

logger = logging.getLogger(__name__)

# What the PUT ended with: an HTTP status, or why there was no response.
Outcome = int | httpx.TransportError | TimeoutError


class Action(Enum):
    ACK = "ack"
    RETRY = "retry"  # reject(requeue=True): delayed retry, then the DLQ
    DEAD_LETTER = "dead_letter"  # reject(requeue=False): straight to the DLQ


def classify(outcome: Outcome) -> Action:
    """Decide what to do with a message from how its ``PUT`` ended."""
    if isinstance(outcome, Exception):
        # Refused, reset, cut off mid-response or timed out: worth another try.
        return Action.RETRY
    if outcome in (200, 201):
        return Action.ACK
    if outcome in (408, 429) or 500 <= outcome <= 599:
        return Action.RETRY
    return Action.DEAD_LETTER


def build_courier(settings: CourierSettings) -> FastStream:
    results_queue = settings.results_queue
    base_url = settings.results_service_base_url
    timeout = settings.delivery_timeout_seconds
    token = CourierToken(settings.jwt_private_key.get_secret_value())
    broker = RabbitBroker(settings.rabbitmq_url)
    # No per-operation timeout: deliver() enforces the total limit itself.
    http = httpx.AsyncClient(timeout=None)
    app = FastStream(broker)

    @app.on_startup
    async def declare_results_queue() -> None:
        # Declare before the subscriber starts consuming from analysis-results.
        await broker.connect()
        await declare_queue(broker, results_queue)

    @app.after_shutdown
    async def close_http() -> None:
        await http.aclose()

    async def put(job_id: UUID, body: bytes) -> Outcome:
        try:
            async with asyncio.timeout(timeout):
                response = await http.put(
                    f"{base_url}/results/{job_id}",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token.get()}",
                    },
                )
        except (httpx.TransportError, TimeoutError) as exc:
            return exc
        return response.status_code

    @broker.subscriber(
        RabbitQueue(results_queue.name, queue_type=QueueType.QUORUM, declare=False),
        channel=Channel(prefetch_count=settings.courier_prefetch),
        ack_policy=AckPolicy.MANUAL,
        # Keep the body as bytes: FastStream's JSON decoding runs before the
        # handler, so a malformed body would fail there and never be rejected.
        decoder=_raw_body,
    )
    async def deliver(message: RabbitMessage) -> None:
        try:
            job_id = _job_id(message.body)
            if job_id is None:
                logger.error(
                    "message_id=%s dead-lettered cause=no valid job_id in the body",
                    message.message_id,
                )
                await message.reject(requeue=False)
                return
            outcome = await put(job_id, message.body)
            match classify(outcome):
                case Action.ACK:
                    await message.ack()
                    logger.info("job_id=%s delivered status=%d", job_id, outcome)
                case Action.RETRY:
                    logger.warning(
                        "job_id=%s retrying cause=%s x-delivery-count=%s",
                        job_id,
                        _cause(outcome, timeout),
                        message.headers.get("x-delivery-count", 0),
                    )
                    await message.reject(requeue=True)
                case Action.DEAD_LETTER:
                    logger.error(
                        "job_id=%s dead-lettered cause=%s",
                        job_id,
                        _cause(outcome, timeout),
                    )
                    await message.reject(requeue=False)
        except Exception:
            # reject, not nack: only reject counts toward the delivery limit.
            logger.exception(
                "message_id=%s requeued after an error", message.message_id
            )
            await message.reject(requeue=True)

    return app


async def _raw_body(message: RabbitMessage) -> bytes:
    return message.body


def _job_id(body: bytes) -> UUID | None:
    """The Result's ``job_id``; parsing it as a UUID keeps it safe in the path."""
    try:
        document = json.loads(body)
        return UUID(document["job_id"])
    except ValueError, TypeError, KeyError, AttributeError:
        return None


def _cause(outcome: Outcome, timeout: float) -> str:
    if isinstance(outcome, TimeoutError):
        return f"no response within {timeout} s"
    if isinstance(outcome, Exception):
        return repr(outcome)
    return f"HTTP {outcome}"


def main() -> None:
    settings = CourierSettings()
    logging.basicConfig(level=settings.log_level)
    asyncio.run(build_courier(settings).run())


if __name__ == "__main__":
    main()
