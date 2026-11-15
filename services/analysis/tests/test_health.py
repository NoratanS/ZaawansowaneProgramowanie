import pytest

pytestmark = pytest.mark.unit


async def test_health_answers_without_the_broker_the_store_or_a_token(
    unit_anonymous_client,
):
    response = await unit_anonymous_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
