import io
from uuid import uuid4

import httpx
import pytest

from fakes import MemoryUploadStore, png

from analysis_service.uploads import url_for
from analysis_service.worker.image_source import ImageSource
from analysis_service.worker.images import ImageFailure

pytestmark = pytest.mark.unit

PUBLIC_URL = "http://analysis.example"


def no_requests(request):
    raise AssertionError(f"an upload must not be fetched over HTTP: {request.url}")


@pytest.fixture
def store():
    return MemoryUploadStore()


@pytest.fixture
async def source_for(store):
    """An image source over the store; its HTTP client refuses every request."""
    refusing = httpx.AsyncClient(transport=httpx.MockTransport(no_requests))

    def build(http=refusing):
        return ImageSource(
            http,
            store,
            public_url=PUBLIC_URL,
            max_bytes=10_000,
            fetch_timeout_seconds=1,
            # The image origin fake is not a real host, which the guard would refuse.
            allowed_hosts=frozenset({"images.example"}),
        )

    yield build
    await refusing.aclose()


@pytest.fixture
def stored_upload(store):
    """Put an object in the upload store as the API would; return its URL."""

    async def put(data):
        upload_id = uuid4()
        await store.put(upload_id, io.BytesIO(data), "image/png")
        return url_for(upload_id, PUBLIC_URL)

    return put


async def test_an_upload_is_read_from_the_store_without_a_request(
    source_for, stored_upload
):
    data = png(width=40, height=30)

    assert await source_for().load(await stored_upload(data)) == data


async def test_an_upload_over_the_cap_is_too_large(source_for, stored_upload):
    with pytest.raises(ImageFailure) as failure:
        await source_for().load(await stored_upload(b"x" * 10_001))

    assert failure.value.code == "image_too_large"


@pytest.mark.parametrize("path", [str(uuid4()), "not-an-id"], ids=["missing", "bad-id"])
async def test_an_upload_that_isnt_there_is_unreachable(source_for, path):
    # url_for takes only an id, so the bad-id URL is built by hand.
    with pytest.raises(ImageFailure) as failure:
        await source_for().load(f"{PUBLIC_URL}/uploads/{path}")

    assert failure.value.code == "image_unreachable"


async def test_any_other_url_is_fetched_over_http(source_for):
    data = png(width=8, height=8)

    def origin(request):
        return httpx.Response(200, content=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(origin)) as http:
        body = await source_for(http).load("http://images.example/people.png")

    assert body == data
