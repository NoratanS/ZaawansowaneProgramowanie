import pytest

from analysis_service.queues import JOBS_QUEUE

pytestmark = pytest.mark.integration

IMAGE_URL = "https://images.example/people.jpg"


def assert_unauthorized(response):
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_post_without_a_token_is_401_and_nothing_is_queued(
    anonymous_client, drain
):
    response = await anonymous_client.post("/analyses", json={"image_url": IMAGE_URL})

    assert_unauthorized(response)
    assert await drain(JOBS_QUEUE) == []


async def test_post_with_a_bad_token_is_401_and_nothing_is_queued(
    anonymous_client, drain, bad_token_for
):
    token = bad_token_for("analysis-service")

    response = await anonymous_client.post(
        "/analyses",
        json={"image_url": IMAGE_URL},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert_unauthorized(response)
    assert await drain(JOBS_QUEUE) == []


async def test_post_with_a_non_bearer_scheme_is_401(anonymous_client, mint_token):
    response = await anonymous_client.post(
        "/analyses",
        json={"image_url": IMAGE_URL},
        headers={"Authorization": f"Basic {mint_token('analysis-service')}"},
    )

    assert_unauthorized(response)


async def test_auth_is_checked_before_the_body(anonymous_client):
    response = await anonymous_client.post("/analyses", json={})

    assert_unauthorized(response)
