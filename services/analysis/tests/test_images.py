import asyncio
import os
import subprocess
import sys

import cv2
import httpx
import numpy as np
import pytest

from analysis_service.images import ImageFailure, decode_image, fetch_image

pytestmark = pytest.mark.unit

URL = "http://images.example/people.jpg"


def client_answering(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def fetch(handler, *, timeout_seconds=1.0, max_bytes=100):
    async with client_answering(handler) as client:
        return await fetch_image(
            client, URL, timeout_seconds=timeout_seconds, max_bytes=max_bytes
        )


async def test_a_2xx_image_comes_back_as_bytes():
    body = await fetch(lambda request: httpx.Response(200, content=b"\xff\xd8jpeg"))

    assert body == b"\xff\xd8jpeg"


async def expect_failure(handler, code, **limits):
    with pytest.raises(ImageFailure) as failure:
        await fetch(handler, **limits)
    assert failure.value.code == code
    assert failure.value.message


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
    run = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return run.stdout.strip()


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
    run = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, analysis_service\n"
            "print(os.environ['OPENCV_IO_MAX_IMAGE_PIXELS'])",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert run.stdout.strip() == "50000000"
