"""Shared integration fixtures: real Postgres and RabbitMQ, started on demand.

The containers start the first time a test asks for them and stop at the end of
the session, so unit runs never touch Docker.
"""

import pytest
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.rabbitmq import RabbitMqContainer


@pytest.fixture(scope="session")
def postgres_url():
    """SQLAlchemy URL (``postgresql+asyncpg://...``) of a throwaway Postgres."""
    with PostgresContainer("postgres:18", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def rabbitmq():
    """A throwaway RabbitMQ container, for tests that need to poke the broker."""
    with RabbitMqContainer("rabbitmq:4.3-management") as rabbitmq:
        yield rabbitmq


@pytest.fixture(scope="session")
def rabbitmq_url(rabbitmq):
    """AMQP URL of the throwaway RabbitMQ."""
    params = rabbitmq.get_connection_params()
    return (
        f"amqp://{rabbitmq.username}:{rabbitmq.password}"
        f"@{params.host}:{params.port}/"
    )
