import logging
from uuid import UUID

import httpx
import pytest

from analysis_service.courier import deliver
from analysis_service.queues import Action

pytestmark = pytest.mark.unit

JOB_ID = "6f1c2a3e-8d4b-4f5a-9c7e-1b2d3e4f5a6b"
BODY = b'{"job_id": "6f1c2a3e-8d4b-4f5a-9c7e-1b2d3e4f5a6b", "status": "succeeded"}'


class FakePut:
    """Answers every PUT with ``outcome`` and records what it was sent."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    async def __call__(self, job_id, body):
        self.calls.append((job_id, body))
        return self.outcome


async def attempt(outcome, body=BODY, delivery_count=0, message_id=None):
    put = FakePut(outcome)
    action = await deliver(
        body, put, delivery_count=delivery_count, timeout=0.2, message_id=message_id
    )
    return action, put


@pytest.mark.parametrize("status", [200, 201])
async def test_a_stored_result_is_acked(status, courier_logs):
    action, put = await attempt(status)

    assert action is Action.ACK
    assert put.calls == [(UUID(JOB_ID), BODY)]
    assert courier_logs(logging.INFO) == [f"job_id={JOB_ID} delivered status={status}"]


@pytest.mark.parametrize(
    "status",
    [408, 429, 500, 502, 503, 504, 520, 522, 524, 599],
)
async def test_a_transient_status_is_retried(status, courier_logs):
    action, _ = await attempt(status, delivery_count=2)

    assert action is Action.RETRY
    assert courier_logs(logging.WARNING) == [
        f"job_id={JOB_ID} retrying cause=HTTP {status} x-delivery-count=2"
    ]
    assert courier_logs(logging.ERROR) == []


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("connection refused"),
        httpx.ReadError("connection reset by peer"),
        httpx.RemoteProtocolError("server disconnected"),
        httpx.ReadTimeout("read timed out"),
    ],
    ids=["refused", "reset", "disconnected", "httpx-timeout"],
)
async def test_a_transport_error_is_retried(error, courier_logs):
    action, _ = await attempt(error)

    assert action is Action.RETRY
    assert courier_logs(logging.WARNING) == [
        f"job_id={JOB_ID} retrying cause={error!r} x-delivery-count=0"
    ]


async def test_no_response_within_the_timeout_is_retried(courier_logs):
    action, _ = await attempt(TimeoutError())

    assert action is Action.RETRY
    assert courier_logs(logging.WARNING) == [
        f"job_id={JOB_ID} retrying cause=no response within 0.2 s x-delivery-count=0"
    ]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 413, 422])
async def test_any_other_client_error_is_dead_lettered(status, courier_logs):
    action, _ = await attempt(status)

    assert action is Action.DEAD_LETTER
    assert courier_logs(logging.ERROR) == [
        f"job_id={JOB_ID} dead-lettered cause=HTTP {status}"
    ]
    assert courier_logs(logging.WARNING) == []


@pytest.mark.parametrize("status", [202, 204, 301, 302])
async def test_an_unexpected_status_is_dead_lettered(status):
    # Nothing but 200/201 means the Result is stored, and retrying won't help.
    action, _ = await attempt(status)

    assert action is Action.DEAD_LETTER


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b"{}", b'{"job_id": "../health"}', b'{"job_id": 7}'],
    ids=["not-json", "not-an-object", "no-job-id", "path-in-job-id", "int-job-id"],
)
async def test_a_message_without_a_job_id_is_dead_lettered_unsent(body, courier_logs):
    action, put = await attempt(201, body=body, message_id="m-1")

    assert action is Action.DEAD_LETTER
    assert put.calls == []
    assert courier_logs(logging.ERROR) == [
        "message_id=m-1 dead-lettered cause=no valid job_id in the body"
    ]
