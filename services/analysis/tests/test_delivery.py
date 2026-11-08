import httpx
import pytest

from analysis_service.courier import classify
from analysis_service.queues import Action

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("status", [200, 201])
def test_a_stored_result_is_acked(status):
    assert classify(status) is Action.ACK


@pytest.mark.parametrize(
    "status",
    [408, 429, 500, 502, 503, 504, 520, 522, 524, 599],
)
def test_a_transient_status_is_retried(status):
    assert classify(status) is Action.RETRY


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("connection refused"),
        httpx.ReadError("connection reset by peer"),
        httpx.RemoteProtocolError("server disconnected"),
        httpx.ReadTimeout("read timed out"),
        TimeoutError(),
    ],
    ids=["refused", "reset", "disconnected", "httpx-timeout", "total-timeout"],
)
def test_a_transient_error_is_retried(error):
    assert classify(error) is Action.RETRY


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 413, 422])
def test_any_other_client_error_is_dead_lettered(status):
    assert classify(status) is Action.DEAD_LETTER


@pytest.mark.parametrize("status", [202, 204, 301, 302])
def test_an_unexpected_status_is_dead_lettered(status):
    # Nothing but 200/201 means the Result is stored, and retrying won't help.
    assert classify(status) is Action.DEAD_LETTER
