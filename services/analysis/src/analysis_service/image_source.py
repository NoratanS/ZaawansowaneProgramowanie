"""Where the Worker gets an Analysis Job's image: the Upload store or HTTP."""

from collections.abc import Collection
from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

import httpx

from analysis_service.images import ImageFailure, fetch_image, read_capped
from analysis_service.uploads import StoredUpload, upload_id_in


class Uploads(Protocol):
    """The part of the Upload store an image source reads from."""

    def open(
        self, upload_id: UUID
    ) -> AbstractAsyncContextManager[StoredUpload | None]: ...


class ImageSource:
    """Loads the image at a URL.

    A bad or missing image raises ``ImageFailure``; a store outage raises as
    is, so the job is retried.
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        store: Uploads,
        *,
        public_url: str,
        max_bytes: int,
        fetch_timeout_seconds: float,
        allowed_hosts: Collection[str],
    ) -> None:
        self._http = http
        self._store = store
        self._public_url = public_url
        self._max_bytes = max_bytes
        self._fetch_timeout_seconds = fetch_timeout_seconds
        self._allowed_hosts = allowed_hosts

    async def load(self, image_url: str) -> bytearray:
        # Uploads are read by key, so the SSRF guard has nothing to check.
        upload_id = upload_id_in(image_url, self._public_url)
        if upload_id is not None:
            async with self._store.open(upload_id) as upload:
                if upload is None:
                    raise ImageFailure("image_unreachable", "the upload does not exist")
                return await read_capped(
                    upload.chunks, self._max_bytes, length=upload.length
                )
        return await fetch_image(
            self._http,
            image_url,
            timeout_seconds=self._fetch_timeout_seconds,
            max_bytes=self._max_bytes,
            allowed_hosts=self._allowed_hosts,
        )
