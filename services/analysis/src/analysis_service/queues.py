"""Queue topology shared by every process that touches a queue.

Each queue is a quorum queue with native delayed retry and a delivery limit.
After the limit, the broker dead-letters the message through ``<queue>.dlx``
(fanout) into ``<queue>.dlq``. All of it is declared from code, not policies.
"""

from dataclasses import dataclass
from typing import Any

from faststream.rabbit import (
    ExchangeType,
    QueueType,
    RabbitBroker,
    RabbitExchange,
    RabbitQueue,
)


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


async def declare_queue(broker: RabbitBroker, config: QueueConfig) -> None:
    """Declare the DLX, the DLQ bound to it, then the work queue."""
    dlx = await broker.declare_exchange(
        RabbitExchange(config.dlx, type=ExchangeType.FANOUT, durable=True)
    )
    dlq = await broker.declare_queue(
        RabbitQueue(config.dlq, queue_type=QueueType.QUORUM)
    )
    await dlq.bind(dlx)
    await broker.declare_queue(
        RabbitQueue(
            config.name,
            queue_type=QueueType.QUORUM,
            arguments=queue_arguments(config),
        )
    )
