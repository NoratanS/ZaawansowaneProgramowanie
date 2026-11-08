import json
from uuid import UUID, uuid4

import pytest

from analysis_service.queues import JOBS_QUEUE
from analysis_service.uploads import url_for

pytestmark = pytest.mark.integration

JPEG = b"\xff\xd8\xff\xe0 not really a jpeg"


async def test_each_uploaded_file_becomes_a_queued_job(client, drain, stored_keys):
    files = [
        ("files", ("one.jpg", JPEG, "image/jpeg")),
        ("files", ("two.png", b"\x89PNG", "image/png")),
        ("files", ("notes.txt", b"hello", "text/plain")),
    ]

    response = await client.post("/uploads", files=files)

    assert response.status_code == 202
    accepted = response.json()
    assert [item["filename"] for item in accepted] == [
        "one.jpg",
        "two.png",
        "notes.txt",
    ]
    for item in accepted:
        job_id = UUID(item["job_id"])
        assert item["result_url"] == f"http://results.example/results/{job_id}"
    jobs = [json.loads(m.body) for m in await drain(JOBS_QUEUE)]
    assert [job["job_id"] for job in jobs] == [item["job_id"] for item in accepted]
    upload_ids = sorted(await stored_keys())
    assert sorted(job["image_url"] for job in jobs) == sorted(
        url_for(UUID(upload_id), "http://analysis.example/uploads")
        for upload_id in upload_ids
    )


def jpegs(count):
    return [("files", (f"{n}.jpg", JPEG, "image/jpeg")) for n in range(count)]


async def test_a_hundred_files_are_accepted(client, drain):
    response = await client.post("/uploads", files=jpegs(100))

    assert response.status_code == 202
    assert len(await drain(JOBS_QUEUE)) == 100


@pytest.mark.parametrize(
    "files, code",
    [
        (jpegs(101), 422),
        ([], 422),
        (
            [
                *jpegs(2),
                ("files", ("big.jpg", b"x" * (11 * 1024 * 1024), "image/jpeg")),
            ],
            413,
        ),
    ],
    ids=["101-files", "no-files", "11-mb-file"],
)
async def test_a_broken_limit_rejects_the_whole_request(
    client, drain, stored_keys, files, code
):
    if files:
        response = await client.post("/uploads", files=files)
    else:
        response = await client.post("/uploads", data={"other": "field"})

    assert response.status_code == code
    assert await drain(JOBS_QUEUE) == []
    assert await stored_keys() == []


async def test_uploads_need_a_client_token(anonymous_client, drain, stored_keys):
    response = await anonymous_client.post("/uploads", files=jpegs(1))

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert await drain(JOBS_QUEUE) == []
    assert await stored_keys() == []


async def test_uploads_refuse_a_courier_token(client, mint_token, drain):
    courier = {"Authorization": f"Bearer {mint_token('results-service')}"}

    response = await client.post("/uploads", files=jpegs(1), headers=courier)

    assert response.status_code == 401
    assert await drain(JOBS_QUEUE) == []


async def test_an_unqueued_upload_gives_503(client, channel):
    await channel.queue_delete(JOBS_QUEUE)

    response = await client.post("/uploads", files=jpegs(2))

    assert response.status_code == 503


async def upload_one(client, drain, name, data, content_type):
    response = await client.post(
        "/uploads", files=[("files", (name, data, content_type))]
    )
    assert response.status_code == 202
    [message] = await drain(JOBS_QUEUE)
    return json.loads(message.body)["image_url"].removeprefix("http://analysis.example")


@pytest.mark.parametrize(
    "content_type, served_as",
    [
        ("image/jpeg", "image/jpeg"),
        ("image/png", "image/png"),
        ("text/plain", "application/octet-stream"),
        ("text/html", "application/octet-stream"),
    ],
)
async def test_an_upload_is_served_back_without_a_token(
    client, anonymous_client, drain, content_type, served_as
):
    path = await upload_one(client, drain, "file", JPEG, content_type)

    response = await anonymous_client.get(path)

    assert response.status_code == 200
    assert response.content == JPEG
    assert response.headers["content-type"] == served_as
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_a_served_upload_cannot_run_script(client, drain):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    path = await upload_one(client, drain, "x.svg", svg, "image/svg+xml")

    response = await client.get(path)

    # Opened directly, an SVG would run its script on the API's origin.
    assert response.headers["content-security-policy"] == "sandbox"


async def test_an_upload_larger_than_a_chunk_streams_back_whole(client, drain):
    data = bytes(range(256)) * 1024  # 256 KiB: several chunks
    path = await upload_one(client, drain, "big.jpg", data, "image/jpeg")

    response = await client.get(path)

    assert response.content == data
    assert response.headers["content-length"] == str(len(data))


async def test_an_unknown_upload_is_404(anonymous_client):
    response = await anonymous_client.get(f"/uploads/{uuid4()}")

    assert response.status_code == 404
