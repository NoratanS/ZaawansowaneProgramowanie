"""Loading and decoding the image an Analysis Job points at.

An upload is read from the Upload store by key; any other URL is fetched
over HTTP.
"""

import asyncio
import ipaddress
import socket
from collections.abc import (
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Collection,
)
from contextlib import AsyncExitStack, asynccontextmanager

import cv2
import httpx
import numpy as np

from analysis_service.messages import ErrorCode
from analysis_service.settings import WorkerSettings

# Lazy: uploads imports ImageFailure from this module.
lazy from analysis_service.uploads import UploadStorage, open_store, upload_id_in

# Wikimedia answers 403 to the default python-httpx User-Agent; it wants
# one that names the app and a contact: https://w.wiki/4wJS
USER_AGENT = (
    "people-counter/0.1 (+https://github.com/NoratanS/ZaawansowaneProgramowanie)"
)

LoadImage = Callable[[str], Awaitable[bytes | bytearray]]
"""Reads the image at a URL; raises ``ImageFailure`` if it can't."""


class ImageFailure(Exception):
    """The image can't be analysed; the job ends as a failed Result."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@asynccontextmanager
async def open_image_source(settings: WorkerSettings) -> AsyncIterator[LoadImage]:
    """Open the HTTP client and the Upload store; yield ``load`` over them."""
    async with AsyncExitStack() as stack:
        # No per-operation timeout: fetch_image enforces the total limit itself,
        # and httpx's 5 s default would cut it short when the limit is longer.
        http = await stack.enter_async_context(
            httpx.AsyncClient(timeout=None, headers={"User-Agent": USER_AGENT})
        )
        # The API creates the bucket, not the Worker.
        store = await stack.enter_async_context(open_store(settings))
        yield image_loader(
            http,
            store,
            public_url=settings.analysis_public_url,
            max_bytes=settings.image_max_bytes,
            fetch_timeout_seconds=settings.image_fetch_timeout_seconds,
            allowed_hosts=settings.image_allowed_hosts,
        )


def image_loader(
    http: httpx.AsyncClient,
    store: UploadStorage,
    *,
    public_url: str,
    max_bytes: int,
    fetch_timeout_seconds: float,
    allowed_hosts: Collection[str],
) -> LoadImage:
    """``load(url)`` over this client and store.

    A bad or missing image raises ``ImageFailure``; a store outage raises as
    is, so the job is retried.
    """

    async def load(image_url: str) -> bytearray:
        # Uploads are read by key, so the SSRF guard has nothing to check.
        upload_id = upload_id_in(image_url, public_url)
        if upload_id is not None:
            async with store.open(upload_id) as upload:
                if upload is None:
                    raise ImageFailure("image_unreachable", "the upload does not exist")
                return await read_capped(upload.chunks, max_bytes, length=upload.length)
        return await fetch_image(
            http,
            image_url,
            timeout_seconds=fetch_timeout_seconds,
            max_bytes=max_bytes,
            allowed_hosts=allowed_hosts,
        )

    return load


async def fetch_image(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout_seconds: float,
    max_bytes: int,
    allowed_hosts: Collection[str],
) -> bytearray:
    """Download the image, within ``timeout_seconds`` in total.

    A host outside ``allowed_hosts`` must resolve to public addresses only.
    """
    try:
        async with asyncio.timeout(timeout_seconds):
            await _check_host(httpx.URL(url).host, allowed_hosts)
            return await _download(client, url, max_bytes)
    except TimeoutError as exc:
        raise ImageFailure(
            "image_unreachable", f"the image took over {timeout_seconds} s to fetch"
        ) from exc
    except (httpx.HTTPError, httpx.InvalidURL, httpx.StreamError) as exc:
        raise ImageFailure(
            "image_unreachable", f"the image could not be fetched: {exc!r}"
        ) from exc


async def _check_host(host: str, allowed_hosts: Collection[str]) -> None:
    """Refuse a host that resolves to any loopback, private or other internal address.

    httpx resolves the host again when it connects, so a host that answers
    differently the second time (DNS rebinding) gets through. Accepted: the
    stack runs locally, behind JWT.
    """
    if host in allowed_hosts:
        return
    try:
        addresses = await _resolve(host)
    except socket.gaierror as exc:
        raise ImageFailure(
            "image_unreachable", f"the image host could not be resolved: {exc!r}"
        ) from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        # is_global is False for loopback, private, link-local, reserved and
        # unspecified (IPv4-mapped IPv6 included); some multicast is "global".
        if not ip.is_global or ip.is_multicast:
            raise ImageFailure(
                "image_url_forbidden", f"the image host {host} is an internal address"
            )


async def _resolve(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, None, type=socket.SOCK_STREAM
    )
    # Drop an IPv6 scope id ("fe80::1%eth0"); ip_address can't parse it.
    return [str(info[4][0]).split("%")[0] for info in infos]


async def _download(client: httpx.AsyncClient, url: str, max_bytes: int) -> bytearray:
    async with client.stream("GET", url) as response:
        if not response.is_success:
            raise ImageFailure(
                "image_unreachable", f"the image host answered {response.status_code}"
            )
        length = response.headers.get("Content-Length", "")
        return await read_capped(
            response.aiter_bytes(),
            max_bytes,
            length=int(length) if length.isdigit() else None,
        )


async def read_capped(
    chunks: AsyncIterable[bytes], max_bytes: int, *, length: int | None = None
) -> bytearray:
    """Read ``chunks`` whole, failing once they pass ``max_bytes``.

    A declared ``length`` over the cap fails before anything is read. It may
    lie or be missing, so the body is capped as it arrives too.
    """
    too_large = ImageFailure(
        "image_too_large", f"the image is over the {max_bytes}-byte limit"
    )
    if length is not None and length > max_bytes:
        raise too_large
    body = bytearray()
    async for chunk in chunks:
        body += chunk
        if len(body) > max_bytes:
            raise too_large
    return body


def decode_image(data: bytes | bytearray) -> np.ndarray:
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
