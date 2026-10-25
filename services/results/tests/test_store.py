from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from results_service import store

pytestmark = pytest.mark.integration


async def test_an_exhausted_connection_pool_is_unavailable(database_url):
    engine = create_async_engine(
        database_url, pool_size=1, max_overflow=0, pool_timeout=0.1
    )
    try:
        async with engine.connect():  # holds the only connection
            with pytest.raises(store.DatabaseUnavailable):
                await store.get(engine, uuid4())
    finally:
        await engine.dispose()
