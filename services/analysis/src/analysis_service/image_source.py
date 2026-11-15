"""Where the Worker gets an Analysis Job's image: the Upload store or HTTP."""

import httpx

from analysis_service.images import fetch_image
from analysis_service.settings import WorkerSettings
from analysis_service.uploads import UploadStore, upload_id_in


class ImageSource:
    """Loads the image at a URL.

    A bad or missing image raises ``ImageFailure``; a store outage raises as
    is, so the job is retried.
    """

    def __init__(
        self, http: httpx.AsyncClient, store: UploadStore, settings: WorkerSettings
    ) -> None:
        self._http = http
        self._store = store
        self._settings = settings

    async def load(self, image_url: str) -> bytearray:
        settings = self._settings
        # Uploads are read by key, so the SSRF guard has nothing to check.
        upload_id = upload_id_in(image_url, settings.uploads_base_url)
        if upload_id is not None:
            return await self._store.read_image(upload_id, settings.image_max_bytes)
        return await fetch_image(
            self._http,
            image_url,
            timeout_seconds=settings.image_fetch_timeout_seconds,
            max_bytes=settings.image_max_bytes,
            allowed_hosts=settings.image_allowed_hosts,
        )
