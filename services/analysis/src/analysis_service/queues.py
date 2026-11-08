"""The work queues: their topology, and publishing to and consuming from them.

Each queue is a quorum queue with native delayed retry and a delivery limit.
After the limit, the broker dead-letters the message through ``<queue>.dlx``
(fanout) into ``<queue>.dlq``. All of it is declared from code, not policies.
"""

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from aiormq.exceptions import AMQPError, ChannelInvalidStateError
from faststream import AckPolicy
from faststream.rabbit import (
    ExchangeType,
    QueueType,
    RabbitBroker,
    RabbitExchange,
    RabbitQueue,
)
from faststream.rabbit.annotations import RabbitMessage
from faststream.rabbit.schemas import Channel

JOBS_QUEUE = "analysis-jobs"
RESULTS_QUEUE = "analysis-results"

# How long a publisher waits for the broker to confirm a message.
PUBLISH_TIMEOUT_SECONDS = 5.0

logger = logging.getLogger(__name__)


class Action(Enum):
    ACK = "ack"
    RETRY = "retry"  # reject(requeue=True): delayed retry, then the DLQ
    DEAD_LETTER = "dead_letter"  # reject(requeue=False): straight to the DLQ


# Gets a message's raw body, headers and message_id; says what to do with it.
Handler = Callable[[bytes, Mapping[str, Any], str | None], Awaitable[Action]]


class NotQueued(Exception):
    """The broker did not confirm a published message onto its queue."""


@dataclass(frozen=True)
class QueueConfig:
    name: str
    retry_min_seconds: float
    retry_max_seconds: float
    delivery_limit: int

    def __post_init__(self) -> None:
        if self.retry_min_seconds > self.retry_max_seconds:
            raise ValueError(
                f"{self.name}: retry_min_seconds must not exceed retry_max_seconds"
            )

    @property
    def dlx(self) -> str:
        return f"{self.name}.dlx"

    @property
    def dlq(self) -> str:
        return f"{self.name}.dlq"


def _ms(seconds: float) -> int:
    return round(seconds * 1000)


def queue_arguments(config: QueueConfig) -> dict[str, Any]:
    """A work queue's declaration arguments; ``RabbitQueue`` adds its type."""
    return {
        # Delay only redeliveries that count as failed (reject, crash).
        "x-delayed-retry-type": "failed",
        "x-delayed-retry-min": _ms(config.retry_min_seconds),
        "x-delayed-retry-max": _ms(config.retry_max_seconds),
        "x-delivery-limit": config.delivery_limit,
        "x-dead-letter-exchange": config.dlx,
        # Confirmed dead-lettering; RabbitMQ requires reject-publish with it.
        "x-dead-letter-strategy": "at-least-once",
        "x-overflow": "reject-publish",
    }


def confirming_broker(url: str) -> RabbitBroker:
    """A broker whose publishes fail when unroutable (``on_return_raises``)."""
    return RabbitBroker(url, default_channel=Channel(on_return_raises=True))


class Queue:
    """One work queue: declares its topology, publishes to it, consumes from it."""

    def __init__(self, broker: RabbitBroker, config: QueueConfig) -> None:
        self._broker = broker
        self._config = config

    async def declare(self) -> None:
        """Declare the DLX, the DLQ bound to it, then the work queue."""
        config = self._config
        dlx = await self._broker.declare_exchange(
            RabbitExchange(config.dlx, type=ExchangeType.FANOUT, durable=True)
        )
        dlq = await self._broker.declare_queue(
            RabbitQueue(config.dlq, queue_type=QueueType.QUORUM)
        )
        await dlq.bind(dlx)
        await self._broker.declare_queue(
            RabbitQueue(
                config.name,
                queue_type=QueueType.QUORUM,
                arguments=queue_arguments(config),
            )
        )

    async def publish(self, message: Any, message_id: str) -> None:
        """Publish persistently and wait for the confirm, or raise ``NotQueued``."""
        try:
            await self._broker.publish(
                message,
                queue=self._config.name,
                persist=True,
                message_id=message_id,
                timeout=PUBLISH_TIMEOUT_SECONDS,
            )
        except (
            AMQPError,  # returned (unroutable) or nacked by the broker
            ChannelInvalidStateError,  # connection lost, reconnect pending
            TimeoutError,  # no confirm within PUBLISH_TIMEOUT_SECONDS
        ) as exc:
            raise NotQueued(f"message_id={message_id} not confirmed") from exc

    def consume(self, handler: Handler, prefetch: int) -> None:
        """Hand each message to ``handler``; call before the broker starts."""

        @self._broker.subscriber(
            RabbitQueue(self._config.name, queue_type=QueueType.QUORUM, declare=False),
            channel=Channel(prefetch_count=prefetch),
            ack_policy=AckPolicy.MANUAL,
            # Keep the body as bytes: FastStream's JSON decoding runs before the
            # handler, so a malformed body would fail there and never be rejected.
            decoder=_raw_body,
        )
        async def on_message(message: RabbitMessage) -> None:
            try:
                action = await handler(
                    message.body, message.headers, message.message_id
                )
            except Exception:
                logger.exception(
                    "message_id=%s requeued after an error", message.message_id
                )
                action = Action.RETRY
            match action:
                case Action.ACK:
                    await message.ack()
                case Action.RETRY:
                    # reject, not nack: only reject counts toward the delivery
                    # limit, so a message that keeps failing ends up in the DLQ.
                    await message.reject(requeue=True)
                case Action.DEAD_LETTER:
                    await message.reject(requeue=False)


async def _raw_body(message: RabbitMessage) -> bytes:
    return message.body
