import asyncio
import struct
from contextlib import asynccontextmanager

import asyncpg
import httpx
import pytest
from alembic import command
from alembic.config import Config

from results_service.app import create_app
from results_service.settings import ResultsSettings

# Nothing listens on port 1, so any query fails with a connection error.
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none"


@asynccontextmanager
async def http_client(settings):
    """An HTTP client for the Results Service, with its lifespan running."""
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://results"
        ) as client:
            yield client


@pytest.fixture
async def unreachable_db_client():
    async with http_client(
        ResultsSettings(database_url=UNREACHABLE_DATABASE_URL)
    ) as client:
        yield client


# FATAL ErrorResponses Postgres sends instead of accepting a connection.
FATAL_ON_CONNECT = {
    "starting up": (b"57P03", b"the database system is starting up"),
    "admin shutdown": (b"57P01", b"terminating connection due to administrator"),
}
_SSL_REQUEST_CODE = 80877103


def _answer_with_fatal(sqlstate, message):
    error = b"".join([b"SFATAL\0", b"C" + sqlstate + b"\0", b"M" + message + b"\0"])
    error += b"\0"

    async def answer(reader, writer):
        while True:
            (length,) = struct.unpack("!I", await reader.readexactly(4))
            body = await reader.readexactly(length - 4)
            if struct.unpack("!I", body[:4]) == (_SSL_REQUEST_CODE,):
                writer.write(b"N")  # no TLS, carry on with the startup message
                continue
            writer.write(b"E" + struct.pack("!I", len(error) + 4) + error)
            await writer.drain()
            writer.close()
            return

    return answer


@pytest.fixture(params=FATAL_ON_CONNECT.values(), ids=FATAL_ON_CONNECT)
async def fatal_on_connect_db_client(request):
    """A client whose database answers every connection with a FATAL error."""
    server = await asyncio.start_server(
        _answer_with_fatal(*request.param), "127.0.0.1", 0
    )
    port = server.sockets[0].getsockname()[1]
    url = f"postgresql+asyncpg://nobody:nothing@127.0.0.1:{port}/none"
    async with server:
        async with http_client(ResultsSettings(database_url=url)) as client:
            yield client


@pytest.fixture(scope="session")
def database_url(postgres_url):
    """The session Postgres, migrated to head once."""
    config = Config()
    config.set_main_option("script_location", "results_service:migrations")
    config.attributes["database_url"] = postgres_url
    command.upgrade(config, "head")
    return postgres_url


@pytest.fixture
async def client(database_url):
    """A Results Service client over an empty ``results`` table."""
    dsn = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute("TRUNCATE results")
    finally:
        await connection.close()

    async with http_client(ResultsSettings(database_url=database_url)) as client:
        yield client
