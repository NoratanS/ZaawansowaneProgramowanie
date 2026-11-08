import httpx
import pytest

from analysis_service.api import create_app
from analysis_service.settings import AnalysisApiSettings

pytestmark = pytest.mark.unit


async def test_health_answers_without_the_broker_the_store_or_a_token(jwt_keys):
    # Nothing listens on port 1, and the lifespan never runs.
    settings = AnalysisApiSettings(
        rabbitmq_url="amqp://nobody:nothing@127.0.0.1:1/",
        results_public_url="http://results.example",
        jwt_public_key=jwt_keys.public,
        s3_endpoint_url="http://127.0.0.1:1",
        s3_access_key="nobody",
        s3_secret_key="nothing",
        analysis_public_url="http://analysis.example",
    )
    transport = httpx.ASGITransport(app=create_app(settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://a") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
