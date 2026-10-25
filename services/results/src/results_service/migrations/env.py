import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from results_service.settings import ResultsSettings


def run_migrations(connection):
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations(database_url):
    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)
    await engine.dispose()


# Tests pass the URL in; `alembic upgrade head` reads DATABASE_URL.
database_url = context.config.attributes.get("database_url")
if database_url is None:
    database_url = ResultsSettings().database_url
asyncio.run(run_async_migrations(database_url))
