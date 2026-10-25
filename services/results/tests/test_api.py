import pytest

pytestmark = pytest.mark.integration


async def test_health_answers_without_the_database(unreachable_db_client):
    response = await unreachable_db_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


SUCCEEDED = {
    "job_id": "0b9d6f4e-6a43-4c39-9f53-2f1f0a6f8c11",
    "image_url": "http://images/people.jpg",
    "status": "succeeded",
    "person_count": 2,
    "detections": [
        {"x": 10, "y": 20, "width": 30, "height": 60, "confidence": 0.91},
        {"x": 50, "y": 25, "width": 28, "height": 58, "confidence": 0.47},
    ],
    "error": None,
    "model": "yolox-s",
    "requested_at": "2026-10-25T12:00:00Z",
    "analyzed_at": "2026-10-25T12:00:03.250000Z",
}


async def test_put_stores_a_new_result(client):
    response = await client.put(f"/results/{SUCCEEDED['job_id']}", json=SUCCEEDED)

    assert response.status_code == 201
    assert response.json() == SUCCEEDED


async def test_repeat_put_returns_the_stored_result_unchanged(client):
    url = f"/results/{SUCCEEDED['job_id']}"
    await client.put(url, json=SUCCEEDED)
    redelivered = {**SUCCEEDED, "person_count": 0, "detections": []}

    response = await client.put(url, json=redelivered)

    assert response.status_code == 200
    assert response.json() == SUCCEEDED
    assert (await client.get(url)).json() == SUCCEEDED


async def test_get_returns_a_stored_result(client):
    await client.put(f"/results/{SUCCEEDED['job_id']}", json=SUCCEEDED)

    response = await client.get(f"/results/{SUCCEEDED['job_id']}")

    assert response.status_code == 200
    assert response.json() == SUCCEEDED


async def test_get_of_an_unknown_id_is_404(client):
    response = await client.get("/results/7d3f5c1a-0000-4000-8000-000000000000")

    assert response.status_code == 404


async def test_get_of_a_non_uuid_is_422(client):
    response = await client.get("/results/not-a-uuid")

    assert response.status_code == 422


FAILED_RESULT = {
    "job_id": "5e2c8a7b-1d4f-4e6a-8b3c-9f0d1e2a3b4c",
    "image_url": "https://example.com/cat.txt",
    "status": "failed",
    "person_count": None,
    "detections": None,
    "error": {"code": "not_an_image", "message": "The file is not an image."},
    "model": "yolox-s",
    "requested_at": "2026-10-25T12:00:00Z",
    "analyzed_at": "2026-10-25T12:00:01Z",
}


async def test_put_stores_a_failed_result(client):
    response = await client.put(
        f"/results/{FAILED_RESULT['job_id']}", json=FAILED_RESULT
    )

    assert response.status_code == 201
    assert response.json() == FAILED_RESULT


def _with_box(**changes):
    box = {**SUCCEEDED["detections"][0], **changes}
    return {**SUCCEEDED, "person_count": 1, "detections": [box]}


SHAPE_VIOLATIONS = {
    "path and body ids differ": {
        **SUCCEEDED,
        "job_id": "11111111-2222-4333-8444-555555555555",
    },
    "succeeded with an error": {
        **SUCCEEDED,
        "error": {"code": "not_an_image", "message": "nope"},
    },
    "succeeded without detections": {**SUCCEEDED, "detections": None},
    "succeeded without a count": {**SUCCEEDED, "person_count": None},
    "failed with a count": {
        **FAILED_RESULT,
        "job_id": SUCCEEDED["job_id"],
        "person_count": 0,
    },
    "failed with detections": {
        **FAILED_RESULT,
        "job_id": SUCCEEDED["job_id"],
        "detections": [],
    },
    "failed without an error": {
        **FAILED_RESULT,
        "job_id": SUCCEEDED["job_id"],
        "error": None,
    },
    "count differs from detections": {**SUCCEEDED, "person_count": 3},
    "negative count": {**SUCCEEDED, "person_count": -1, "detections": []},
    "unknown error code": {
        **FAILED_RESULT,
        "job_id": SUCCEEDED["job_id"],
        "error": {"code": "model_crashed", "message": "boom"},
    },
    "negative x": _with_box(x=-1),
    "negative y": _with_box(y=-1),
    "zero width": _with_box(width=0),
    "zero height": _with_box(height=0),
    "fractional box": _with_box(x=1.5),
    "confidence above 1": _with_box(confidence=1.01),
    "confidence below 0": _with_box(confidence=-0.01),
    "unknown status": {**SUCCEEDED, "status": "pending"},
    "naive requested_at": {**SUCCEEDED, "requested_at": "2026-10-25T12:00:00"},
    "naive analyzed_at": {**SUCCEEDED, "analyzed_at": "2026-10-25T12:00:03"},
}


@pytest.mark.parametrize("body", SHAPE_VIOLATIONS.values(), ids=SHAPE_VIOLATIONS)
async def test_put_rejects_a_misshapen_result(client, body):
    url = f"/results/{SUCCEEDED['job_id']}"

    response = await client.put(url, json=body)

    assert response.status_code == 422
    assert (await client.get(url)).status_code == 404


async def test_timestamps_come_back_in_utc(client):
    body = {**SUCCEEDED, "requested_at": "2026-10-25T14:00:00+02:00"}

    response = await client.put(f"/results/{SUCCEEDED['job_id']}", json=body)

    assert response.json()["requested_at"] == "2026-10-25T12:00:00Z"


def _failed_with_id(n):
    return {**FAILED_RESULT, "job_id": f"00000000-0000-4000-8000-{n:012d}"}


async def _put_all(client, bodies):
    for body in bodies:
        response = await client.put(f"/results/{body['job_id']}", json=body)
        assert response.status_code == 201


async def test_list_of_nothing_is_an_empty_array(client):
    response = await client.get("/results")

    assert response.status_code == 200
    assert response.json() == []


async def test_list_is_newest_stored_first_and_includes_failed(client):
    await _put_all(client, [SUCCEEDED, FAILED_RESULT])

    response = await client.get("/results")

    assert response.json() == [FAILED_RESULT, SUCCEEDED]


async def test_list_pages_with_limit_and_offset(client):
    first, second, third = (_failed_with_id(n) for n in range(3))
    await _put_all(client, [first, second, third])

    response = await client.get("/results", params={"limit": 1, "offset": 1})

    assert response.json() == [second]


async def test_list_returns_50_by_default(client):
    await _put_all(client, [_failed_with_id(n) for n in range(51)])

    response = await client.get("/results")

    assert len(response.json()) == 50


async def test_list_accepts_the_largest_limit(client):
    response = await client.get("/results", params={"limit": 200})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 201},
        {"limit": "ten"},
        {"offset": -1},
    ],
    ids=["limit 0", "limit 201", "limit not a number", "negative offset"],
)
async def test_list_rejects_out_of_range_paging(client, params):
    response = await client.get("/results", params=params)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "method, url, body",
    [
        ("PUT", f"/results/{SUCCEEDED['job_id']}", SUCCEEDED),
        ("GET", f"/results/{SUCCEEDED['job_id']}", None),
        ("GET", "/results", None),
    ],
    ids=["put", "get one", "list"],
)
async def test_unreachable_database_is_503(unreachable_db_client, method, url, body):
    response = await unreachable_db_client.request(method, url, json=body)

    assert response.status_code == 503


async def test_database_still_starting_up_is_503(starting_up_db_client):
    response = await starting_up_db_client.get("/results")

    assert response.status_code == 503
