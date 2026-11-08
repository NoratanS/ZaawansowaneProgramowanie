"""Uploaded photos, kept in an S3-compatible store (RustFS in compose).

Each upload is one object keyed by a new UUID. The API stores them and
serves them back; the Worker reads them by key instead of over HTTP.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import BinaryIO
from uuid import UUID

from aiobotocore.session import get_session
from botocore.config import Config
from botocore.exceptions import ClientError

from analysis_service.images import ImageFailure
from analysis_service.settings import UploadSettings

UPLOADS_BUCKET = "uploads"
CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class StoredUpload:
    content_type: str
    length: int
    chunks: AsyncIterator[bytes]


class UploadStore:
    def __init__(self, client) -> None:
        self._client = client
        self._bucket = UPLOADS_BUCKET

    async def create_bucket_if_missing(self) -> None:
        try:
            await self._client.head_bucket(Bucket=self._bucket)
        except ClientError as exc:
            if _status(exc) != 404:
                raise
            await self._client.create_bucket(Bucket=self._bucket)

    async def put(self, upload_id: UUID, file: BinaryIO, content_type: str) -> None:
        await self._client.put_object(
            Bucket=self._bucket,
            Key=str(upload_id),
            Body=file,
            ContentType=content_type,
        )

    @asynccontextmanager
    async def open(self, upload_id: UUID) -> AsyncIterator[StoredUpload | None]:
        """The stored object, or ``None`` if there is none with this id."""
        try:
            response = await self._client.get_object(
                Bucket=self._bucket, Key=str(upload_id)
            )
        except ClientError as exc:
            if _status(exc) != 404:
                raise
            yield None
            return
        async with response["Body"] as body:
            yield StoredUpload(
                content_type=response.get("ContentType", ""),
                length=response["ContentLength"],
                chunks=body.iter_chunks(CHUNK_BYTES),
            )

    async def read_image(self, upload_id: UUID, max_bytes: int) -> bytearray:
        """The upload's bytes, failing as a fetched image would."""
        async with self.open(upload_id) as upload:
            if upload is None:
                raise ImageFailure("image_unreachable", "the upload does not exist")
            too_large = ImageFailure(
                "image_too_large", f"the image is over the {max_bytes}-byte limit"
            )
            if upload.length > max_bytes:
                raise too_large
            body = bytearray()
            async for chunk in upload.chunks:
                body += chunk
                if len(body) > max_bytes:
                    raise too_large
            return body


def _status(exc: ClientError) -> int | None:
    return exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")


def upload_id_in(url: str, uploads_base_url: str) -> UUID | None:
    """The upload id if ``url`` points at an upload, else ``None``.

    A URL under the uploads path whose last part isn't an id names no upload,
    so it fails like a missing one.
    """
    prefix = uploads_base_url + "/"
    if not url.startswith(prefix):
        return None
    try:
        return UUID(url.removeprefix(prefix))
    except ValueError as exc:
        raise ImageFailure("image_unreachable", "the URL names no upload") from exc


@asynccontextmanager
async def open_store(settings: UploadSettings) -> AsyncIterator[UploadStore]:
    session = get_session()
    async with session.create_client(
        "s3",
        endpoint_url=str(settings.s3_endpoint_url),
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        # RustFS ignores the region, but botocore needs one to sign.
        region_name="us-east-1",
        # Host-style addressing would ask for uploads.s3:9000, which doesn't resolve.
        config=Config(s3={"addressing_style": "path"}),
    ) as client:
        yield UploadStore(client)
