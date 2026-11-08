"""The full compose stack, driven from outside over HTTP.

The stack runs as its own compose project on ports 18000/18001, so it never
touches the dev stack. ``E2E_REUSE_STACK=1`` skips ``up``/``down`` and uses a
stack that is already running; its private key is read from the running Courier.
"""

import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).parents[2]
PROJECT = "people-counter-e2e"
# Where the Workers fetch fixtures from, inside the compose network.
IMAGES_URL = "http://images"
POLL_INTERVAL_SECONDS = 0.5
POLL_TIMEOUT_SECONDS = 60

E2E_ENV = {
    "ANALYSIS_API_PORT": "18000",
    "RESULTS_PORT": "18001",
    "RABBITMQ_MANAGEMENT_PORT": "15673",
    "RABBITMQ_DEFAULT_USER": "e2e",
    "RABBITMQ_DEFAULT_PASS": "e2e",
    "POSTGRES_PASSWORD": "e2e",
}
ANALYSIS_URL = f"http://localhost:{E2E_ENV['ANALYSIS_API_PORT']}"
RESULTS_URL = f"http://localhost:{E2E_ENV['RESULTS_PORT']}"
# Compose interpolates every ``${VAR:?}`` even for stop/start/exec/logs, which
# never recreate a container; for those, any key value will do.
PLACEHOLDER_KEYS = {"JWT_PRIVATE_KEY": "unused", "JWT_PUBLIC_KEY": "unused"}


def compose(*args, keys=PLACEHOLDER_KEYS, capture=False):
    """Run ``docker compose`` against the e2e project."""
    # Process env loses to these, so a dev .env or shell can't leak in.
    env = os.environ | E2E_ENV | keys
    command = [
        "docker",
        "compose",
        "-f",
        "compose.yaml",
        "-f",
        "compose.e2e.yaml",
        "-p",
        PROJECT,
        *args,
    ]
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        capture_output=capture,
    ).stdout


def _poll(check, what):
    """Call ``check`` until it returns something truthy; fail after the timeout."""
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if found := check():
            return found
        time.sleep(POLL_INTERVAL_SECONDS)
    pytest.fail(f"{what} after {POLL_TIMEOUT_SECONDS} s")


@pytest.fixture(scope="session")
def stack(request):
    """Start the stack (unless reused) and return the private key it trusts."""
    if os.environ.get("E2E_REUSE_STACK") == "1":
        yield compose(
            "exec", "-T", "courier", "printenv", "JWT_PRIVATE_KEY", capture=True
        ).strip()
        return
    jwt_keys = request.getfixturevalue("jwt_keys")  # a throwaway pair
    keys = {"JWT_PRIVATE_KEY": jwt_keys.private, "JWT_PUBLIC_KEY": jwt_keys.public}
    try:
        compose("up", "-d", "--build", "--wait", keys=keys)
        yield jwt_keys.private
    finally:
        # Also after a failed `up`, so a half-started stack doesn't linger.
        compose("down", "-v", keys=keys)


@pytest.fixture(scope="session")
def e2e_token(stack, mint_token):
    """Mint a token for any ``aud``, signed with the key the stack trusts."""
    return lambda aud: mint_token(aud, private_key=stack, sub="e2e")


@pytest.fixture(scope="session")
def client_token(e2e_token):
    return e2e_token("analysis-service")


@pytest.fixture(scope="session")
def docker_compose(stack):
    """``compose``, as a fixture so the stack is up before a test uses it."""
    return compose


@pytest.fixture(scope="session")
def analysis_url():
    return ANALYSIS_URL


@pytest.fixture(scope="session")
def results_url():
    return RESULTS_URL


@pytest.fixture(scope="session")
def images_url():
    return IMAGES_URL


@pytest.fixture(scope="session")
def http(stack):
    with httpx.Client(timeout=10) as client:
        yield client


@pytest.fixture(scope="session")
def submit(http, client_token):
    """``POST /analyses`` for a fixture served by ``images``; return the 202."""

    def post_analysis(fixture):
        response = http.post(
            f"{ANALYSIS_URL}/analyses",
            json={"image_url": f"{IMAGES_URL}/{fixture}"},
            headers={"Authorization": f"Bearer {client_token}"},
        )
        assert response.status_code == 202, response.text
        return response

    return post_analysis


@pytest.fixture(scope="session")
def wait_for_result(http):
    """Poll a ``result_url`` until it stops returning ``404``."""

    def fetch(result_url):
        try:
            response = http.get(result_url)
        except httpx.TransportError:
            return None  # the Results Service is restarting
        if response.status_code == 404:
            return None
        assert response.status_code == 200, response.text
        return response.json()

    def wait(result_url):
        return _poll(lambda: fetch(result_url), f"no Analysis Result at {result_url}")

    return wait


@pytest.fixture(scope="session")
def wait_for_log(docker_compose):
    """Poll a service's logs until they contain every one of ``texts``."""

    def logged_all(service, texts):
        logs = docker_compose("logs", service, capture=True)
        return all(text in logs for text in texts)

    def wait(service, *texts):
        _poll(
            lambda: logged_all(service, texts),
            f"{service} never logged all of {texts!r}",
        )

    return wait
