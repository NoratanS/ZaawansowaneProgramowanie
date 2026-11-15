import io
from uuid import uuid4

import httpx
import pytest

from fakes import png

from analysis_service.image_source import ImageSource
from analysis_service.images import ImageFailure
from analysis_service.settings import WorkerSettings
from analysis_service.uploads import open_store, url_for

pytestmark = pytest.mark.integration


def no_requests(request):
    raise AssertionError(f"an upload must not be fetched over HTTP: {request.url}")


@pytest.fixture
def settings(upload_settings):
    return WorkerSettings(
        # The image source never touches the broker.
        rabbitmq_url="amqp://unused",
        image_max_bytes=10_000,
        image_fetch_timeout_seconds=1,
        # The image origin fake listens on localhost, which the guard would refuse.
        image_allowed_hosts=frozenset({"localhost"}),
        **upload_settings,
    )


@pytest.fixture
async def store(settings):
    async with open_store(settings) as store:
        await store.create_bucket_if_missing()
        yield store


@pytest.fixture
async def source_for(settings, store):
    """An image source over the store; its HTTP client refuses every request."""
    refusing = httpx.AsyncClient(transport=httpx.MockTransport(no_requests))

    def build(http=refusing):
        return ImageSource(http, store, settings)

    yield build
    await refusing.aclose()


@pytest.fixture
def stored_upload(settings, store):
    """Put an object in the upload store as the API would; return its URL."""

    async def put(data):
        upload_id = uuid4()
        await store.put(upload_id, io.BytesIO(data), "image/png")
        return url_for(upload_id, settings.uploads_base_url)

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
async def test_an_upload_that_isnt_there_is_unreachable(source_for, settings, path):
    # url_for takes only an id, so the bad-id URL is built by hand.
    with pytest.raises(ImageFailure) as failure:
        await source_for().load(f"{settings.uploads_base_url}/{path}")

    assert failure.value.code == "image_unreachable"


async def test_any_other_url_is_fetched_over_http(source_for, httpserver):
    data = png(width=8, height=8)
    httpserver.expect_request("/people.png").respond_with_data(data)

    async with httpx.AsyncClient() as http:
        body = await source_for(http).load(httpserver.url_for("/people.png"))

    assert body == data
