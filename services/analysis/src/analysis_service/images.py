"""Fetching and decoding the image an Analysis Job points at."""

import asyncio

import cv2
import httpx
import numpy as np

from analysis_service.messages import ErrorCode


class ImageFailure(Exception):
    """The image can't be analysed; the job ends as a failed Result."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def fetch_image(
    client: httpx.AsyncClient, url: str, *, timeout_seconds: float, max_bytes: int
) -> bytes:
    """Download the image, within ``timeout_seconds`` in total."""
    try:
        async with asyncio.timeout(timeout_seconds):
            return await _download(client, url, max_bytes)
    except TimeoutError as exc:
        raise ImageFailure(
            "image_unreachable", f"the image took over {timeout_seconds} s to fetch"
        ) from exc
    except (httpx.HTTPError, httpx.InvalidURL, httpx.StreamError) as exc:
        raise ImageFailure(
            "image_unreachable", f"the image could not be fetched: {exc!r}"
        ) from exc


async def _download(client: httpx.AsyncClient, url: str, max_bytes: int) -> bytes:
    async with client.stream("GET", url) as response:
        if not response.is_success:
            raise ImageFailure(
                "image_unreachable", f"the image host answered {response.status_code}"
            )
        too_large = ImageFailure(
            "image_too_large", f"the image is over the {max_bytes}-byte limit"
        )
        length = response.headers.get("Content-Length", "")
        if length.isdigit() and int(length) > max_bytes:
            raise too_large
        # The header may lie or be missing, so cap the body as it arrives.
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body += chunk
            if len(body) > max_bytes:
                raise too_large
        return bytes(body)


def decode_image(data: bytes) -> np.ndarray:
    """Decode the bytes into a BGR pixel array."""
    image = None
    if data:
        try:
            image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        except cv2.error as exc:
            if "MAX_IMAGE_PIXELS" in str(exc):
                raise ImageFailure(
                    "image_too_large", "the image has too many pixels to decode"
                ) from exc
    if image is None:
        raise ImageFailure("not_an_image", "the URL did not return a decodable image")
    return image
