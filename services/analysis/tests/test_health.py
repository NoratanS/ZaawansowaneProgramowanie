import httpx
import pytest

from analysis_service.api import create_app
from analysis_service.settings import AnalysisApiSettings

pytestmark = pytest.mark.unit


async def test_health_answers_without_the_broker():
    # Nothing listens on port 1, and the lifespan never runs.
    settings = AnalysisApiSettings(
        rabbitmq_url="amqp://nobody:nothing@127.0.0.1:1/",
        results_public_url="http://results.example",
    )
    transport = httpx.ASGITransport(app=create_app(settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://a") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
