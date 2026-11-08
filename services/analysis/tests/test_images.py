import asyncio
import os
import socket
import subprocess
import sys

import cv2
import httpx
import numpy as np
import pytest

from analysis_service import images
from analysis_service.images import (
    ImageFailure,
    decode_image,
    fetch_image,
    read_capped,
)

pytestmark = pytest.mark.unit

URL = "http://images.example/people.jpg"


def ok(request):
    return httpx.Response(200, content=b"\xff\xd8jpeg")


async def fetch(
    handler,
    *,
    url=URL,
    timeout_seconds=1.0,
    max_bytes=100,
    allowed_hosts=frozenset({"images.example"}),
):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await fetch_image(
            client,
            url,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
            allowed_hosts=allowed_hosts,
        )


async def test_a_2xx_image_comes_back_as_bytes():
    body = await fetch(ok)

    assert body == b"\xff\xd8jpeg"


async def expect_failure(handler, code, **limits):
    with pytest.raises(ImageFailure) as failure:
        await fetch(handler, **limits)
    assert failure.value.code == code
    assert failure.value.message


def recorder():
    requests = []

    def record(request):
        requests.append(request)
        return ok(request)

    return record, requests


INTERNAL = {
    "loopback": "127.0.0.1",
    "loopback-v6": "[::1]",
    "private-10": "10.0.0.7",
    "private-172": "172.18.0.3",
    "private-192": "192.168.1.1",
    "metadata": "169.254.169.254",
    "link-local-v6": "[fe80::1]",
    "unique-local-v6": "[fd00::1]",
    "multicast": "224.0.0.1",
    "multicast-global": "233.252.0.1",
    "multicast-v6": "[ff0e::1]",
    "reserved": "240.0.0.1",
    "broadcast": "255.255.255.255",
    "unspecified": "0.0.0.0",
    "unspecified-v6": "[::]",
    "mapped-loopback": "[::ffff:127.0.0.1]",
}


@pytest.mark.parametrize("host", INTERNAL.values(), ids=INTERNAL.keys())
async def test_an_internal_address_is_forbidden_before_any_request(host):
    record, requests = recorder()

    await expect_failure(
        record, "image_url_forbidden", url=f"http://{host}:15672/people.jpg"
    )
    assert requests == []


async def test_a_host_name_that_resolves_internal_is_forbidden():
    record, requests = recorder()

    # localhost resolves from /etc/hosts, so this needs no network.
    await expect_failure(
        record, "image_url_forbidden", url="http://localhost/people.jpg"
    )
    assert requests == []


async def test_one_internal_address_among_public_ones_is_enough(monkeypatch):
    async def resolve(host):
        return ["93.184.215.14", "10.0.0.7"]

    monkeypatch.setattr(images, "_resolve", resolve)
    record, requests = recorder()

    await expect_failure(
        record,
        "image_url_forbidden",
        url="http://images.example/people.jpg",
        allowed_hosts=frozenset(),
    )
    assert requests == []


@pytest.mark.parametrize("host", ["93.184.215.14", "[2606:4700::1111]"])
async def test_a_public_address_is_fetched(host):
    body = await fetch(ok, url=f"http://{host}/people.jpg", allowed_hosts=frozenset())

    assert body == b"\xff\xd8jpeg"


async def test_an_allowed_host_is_fetched_even_if_internal():
    body = await fetch(
        ok, url="http://localhost/people.jpg", allowed_hosts=frozenset({"localhost"})
    )

    assert body == b"\xff\xd8jpeg"


async def test_a_host_that_does_not_resolve_is_unreachable(monkeypatch):
    async def resolve(host):
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    monkeypatch.setattr(images, "_resolve", resolve)

    await expect_failure(
        ok,
        "image_unreachable",
        url="http://nowhere.example/",
        allowed_hosts=frozenset(),
    )


@pytest.mark.parametrize("status", [404, 403, 500, 503, 302, 304])
async def test_a_non_2xx_status_is_unreachable(status):
    await expect_failure(
        lambda request: httpx.Response(status, content=b"nope"), "image_unreachable"
    )


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError,
        httpx.ReadError,
        httpx.RemoteProtocolError,
        # Not HTTPError subclasses, so they need catching on their own.
        lambda message, request: httpx.InvalidURL(message),
        lambda message, request: httpx.StreamClosed(),
    ],
    ids=["connect", "read", "protocol", "invalid-url", "stream"],
)
async def test_a_transport_error_is_unreachable(error):
    def refuse(request):
        raise error("boom", request=request)

    await expect_failure(refuse, "image_unreachable")


async def test_a_slow_host_is_unreachable():
    async def stall(request):
        await asyncio.sleep(1)
        return httpx.Response(200, content=b"late")

    await expect_failure(stall, "image_unreachable", timeout_seconds=0.05)


async def test_the_time_limit_covers_the_whole_body():
    async def trickle():
        for _ in range(10):
            yield b"x"
            await asyncio.sleep(0.02)

    await expect_failure(
        lambda request: httpx.Response(200, content=trickle()),
        "image_unreachable",
        timeout_seconds=0.05,
    )


async def test_a_content_length_over_the_cap_is_too_large():
    def huge(request):
        # Announce more than the cap but send nothing: the header alone decides.
        return httpx.Response(200, headers={"Content-Length": "101"}, content=b"")

    await expect_failure(huge, "image_too_large", max_bytes=100)


async def test_a_streamed_body_over_the_cap_is_too_large():
    async def endless():
        while True:
            yield b"x" * 30
            await asyncio.sleep(0)

    await expect_failure(
        lambda request: httpx.Response(200, content=endless()),
        "image_too_large",
        max_bytes=100,
    )


async def test_a_body_exactly_at_the_cap_is_fine():
    body = await fetch(
        lambda request: httpx.Response(200, content=b"x" * 100), max_bytes=100
    )

    assert len(body) == 100


async def stream(*chunks):
    for chunk in chunks:
        yield chunk


@pytest.mark.parametrize("size", [99, 100], ids=["under", "at"])
async def test_chunks_up_to_the_cap_are_read_whole(size):
    data = bytes(range(size))

    body = await read_capped(stream(data[:40], data[40:]), max_bytes=100)

    assert body == data


async def test_chunks_over_the_cap_are_too_large():
    with pytest.raises(ImageFailure) as failure:
        await read_capped(stream(b"x" * 60, b"x" * 41), max_bytes=100)

    assert failure.value.code == "image_too_large"
    assert failure.value.message == "the image is over the 100-byte limit"


async def test_a_declared_length_over_the_cap_is_too_large_before_reading():
    async def unread():
        raise AssertionError("the body must not be read")
        yield

    with pytest.raises(ImageFailure) as failure:
        await read_capped(unread(), max_bytes=100, length=101)

    assert failure.value.code == "image_too_large"


def test_a_real_image_decodes_to_its_pixels():
    picture = np.zeros((30, 40, 3), dtype=np.uint8)
    ok, png = cv2.imencode(".png", picture)
    assert ok

    image = decode_image(png.tobytes())

    assert image.shape == (30, 40, 3)


@pytest.mark.parametrize(
    "data", [b"", b"<html>not a picture</html>", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20]
)
def test_undecodable_bytes_are_not_an_image(data):
    with pytest.raises(ImageFailure) as failure:
        decode_image(data)

    assert failure.value.code == "not_an_image"


def run_python(script, env):
    run = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return run.stdout.strip()


def decode_in_fresh_process(env):
    # OpenCV reads the pixel cap once at import, so each case needs its own process.
    script = (
        "import cv2, numpy as np\n"
        "from analysis_service.images import ImageFailure, decode_image\n"
        "ok, png = cv2.imencode('.png', np.zeros((40, 40, 3), np.uint8))\n"
        "try:\n"
        "    print(decode_image(png.tobytes()).shape)\n"
        "except ImageFailure as failure:\n"
        "    print(failure.code)\n"
    )
    return run_python(script, {**os.environ, **env})


def test_an_image_over_the_pixel_cap_is_too_large():
    assert decode_in_fresh_process({"OPENCV_IO_MAX_IMAGE_PIXELS": "1000"}) == (
        "image_too_large"
    )


def test_an_image_under_the_pixel_cap_decodes():
    assert decode_in_fresh_process({"OPENCV_IO_MAX_IMAGE_PIXELS": "1600"}) == (
        "(40, 40, 3)"
    )


def test_the_package_sets_a_default_pixel_cap():
    env = {k: v for k, v in os.environ.items() if k != "OPENCV_IO_MAX_IMAGE_PIXELS"}
    script = (
        "import os, analysis_service\nprint(os.environ['OPENCV_IO_MAX_IMAGE_PIXELS'])"
    )
    assert run_python(script, env) == "50000000"
