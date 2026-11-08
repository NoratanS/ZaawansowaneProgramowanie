import pytest

pytestmark = pytest.mark.integration

JOB_ID = "0b9d6f4e-6a43-4c39-9f53-2f1f0a6f8c11"
RESULT = {
    "job_id": JOB_ID,
    "image_url": "http://images/people.jpg",
    "status": "succeeded",
    "person_count": 0,
    "detections": [],
    "error": None,
    "model": "yolox-s",
    "requested_at": "2026-10-25T12:00:00Z",
    "analyzed_at": "2026-10-25T12:00:03Z",
}
URL = f"/results/{JOB_ID}"


def assert_unauthorized(response):
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_put_without_a_token_is_401_and_nothing_is_stored(anonymous_client):
    response = await anonymous_client.put(URL, json=RESULT)

    assert_unauthorized(response)
    assert (await anonymous_client.get(URL)).status_code == 404


async def test_put_with_a_bad_token_is_401_and_nothing_is_stored(
    anonymous_client, bad_token_for
):
    token = bad_token_for("results-service")

    response = await anonymous_client.put(
        URL, json=RESULT, headers={"Authorization": f"Bearer {token}"}
    )

    assert_unauthorized(response)
    assert (await anonymous_client.get(URL)).status_code == 404


async def test_auth_is_checked_before_the_body(anonymous_client):
    response = await anonymous_client.put(URL, json={})

    assert_unauthorized(response)


async def test_reads_need_no_token(client, anonymous_client):
    await client.put(URL, json=RESULT)

    assert (await anonymous_client.get(URL)).status_code == 200
    assert (await anonymous_client.get("/results")).json() == [RESULT]
    assert (await anonymous_client.get("/health")).status_code == 200
