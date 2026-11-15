"""One Delivery attempt of an Analysis Result, and what to do with it after."""

import json
import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

import httpx

from analysis_service.queues import Action, Received

logger = logging.getLogger(__name__)

# What the PUT ended with: an HTTP status, or why there was no response.
Outcome = int | httpx.TransportError | TimeoutError


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


# Sends one Result to the Results Service and reports how the PUT ended.
Put = Callable[[UUID, bytes], Awaitable[Outcome]]


async def deliver(received: Received, put: Put, *, timeout: float) -> Action:
    """One Delivery attempt: PUT the Result in ``received``, say what to do next.

    Its ``delivery_count`` and ``message_id`` only feed the log lines;
    ``timeout`` is the PUT's total limit, named in the cause text when it runs out.
    """
    body = received.body
    job_id = _job_id(body)
    if job_id is None:
        logger.error(
            "message_id=%s dead-lettered cause=no valid job_id in the body",
            received.message_id,
        )
        return Action.DEAD_LETTER
    outcome = await put(job_id, body)
    action = classify(outcome)
    match action:
        case Action.ACK:
            logger.info("job_id=%s delivered status=%d", job_id, outcome)
        case Action.RETRY:
            logger.warning(
                "job_id=%s retrying cause=%s x-delivery-count=%s",
                job_id,
                _cause(outcome, timeout),
                received.delivery_count,
            )
        case Action.DEAD_LETTER:
            logger.error(
                "job_id=%s dead-lettered cause=%s",
                job_id,
                _cause(outcome, timeout),
            )
    return action


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
