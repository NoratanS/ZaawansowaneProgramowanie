import asyncpg
import pytest
from faststream.rabbit import RabbitBroker


@pytest.mark.integration
async def test_postgres_and_rabbitmq_are_reachable(postgres_url, rabbitmq_url):
    dsn = postgres_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(dsn)
    try:
        assert await connection.fetchval("SELECT 1") == 1
    finally:
        await connection.close()

    async with RabbitBroker(rabbitmq_url) as broker:
        assert await broker.ping(timeout=5)
