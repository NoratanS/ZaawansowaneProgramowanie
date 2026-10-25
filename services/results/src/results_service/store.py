"""Reads and writes Analysis Results in the ``results`` table.

Alembic owns the schema; this table definition only describes it for queries.
"""

from contextlib import asynccontextmanager
from uuid import UUID

import asyncpg
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from results_service.models import AnalysisResult

results = sa.Table(
    "results",
    sa.MetaData(),
    sa.Column("job_id", sa.Uuid(), primary_key=True),
    sa.Column("image_url", sa.Text()),
    sa.Column("status", sa.Text()),
    sa.Column("person_count", sa.Integer()),
    sa.Column("detections", postgresql.JSONB(none_as_null=True)),
    sa.Column("error_code", sa.Text()),
    sa.Column("error_message", sa.Text()),
    sa.Column("model", sa.Text()),
    sa.Column("requested_at", sa.DateTime(timezone=True)),
    sa.Column("analyzed_at", sa.DateTime(timezone=True)),
    sa.Column("stored_at", sa.DateTime(timezone=True)),
)

_PUBLIC_COLUMNS = [column for column in results.c if column.name != "stored_at"]

# Errors that mean "no usable connection", seen anywhere in the cause chain.
# OSError covers refused connections, timeouts and DNS failures.
# sa.exc.TimeoutError means every pooled connection stayed busy too long.
_CONNECTION_ERRORS = (
    OSError,
    sa.exc.TimeoutError,
    asyncpg.AdminShutdownError,
    asyncpg.CrashShutdownError,
    asyncpg.CannotConnectNowError,
    asyncpg.TooManyConnectionsError,
    asyncpg.PostgresConnectionError,
)


class DatabaseUnavailable(Exception):
    """The database could not be reached, so the request may succeed later."""


def _is_connection_error(error: BaseException | None) -> bool:
    if isinstance(error, DBAPIError) and error.connection_invalidated:
        return True
    while error is not None:
        if isinstance(error, _CONNECTION_ERRORS):
            return True
        error = error.__cause__
    return False


@asynccontextmanager
async def _connect(engine: AsyncEngine, *, transaction: bool = False):
    try:
        async with engine.begin() if transaction else engine.connect() as connection:
            yield connection
    except Exception as error:
        if _is_connection_error(error):
            raise DatabaseUnavailable() from error
        raise


def _to_row(result: AnalysisResult) -> dict:
    return {
        "job_id": result.job_id,
        "image_url": str(result.image_url),
        "status": result.status,
        "person_count": result.person_count,
        "detections": (
            None
            if result.detections is None
            else [detection.model_dump() for detection in result.detections]
        ),
        "error_code": None if result.error is None else result.error.code,
        "error_message": None if result.error is None else result.error.message,
        "model": result.model,
        "requested_at": result.requested_at,
        "analyzed_at": result.analyzed_at,
    }


def _from_row(row: sa.Row) -> AnalysisResult:
    error = None
    if row.error_code is not None:
        error = {"code": row.error_code, "message": row.error_message}
    return AnalysisResult(
        job_id=row.job_id,
        image_url=row.image_url,
        status=row.status,
        person_count=row.person_count,
        detections=row.detections,
        error=error,
        model=row.model,
        requested_at=row.requested_at,
        analyzed_at=row.analyzed_at,
    )


async def insert_first_write_wins(
    engine: AsyncEngine, result: AnalysisResult
) -> tuple[AnalysisResult, bool]:
    """Store ``result`` unless its job id is taken (first write wins).

    Returns the stored Result and whether this call inserted it.
    """
    insert = (
        postgresql.insert(results)
        .values(_to_row(result))
        .on_conflict_do_nothing(index_elements=["job_id"])
        .returning(*_PUBLIC_COLUMNS)
    )
    async with _connect(engine, transaction=True) as connection:
        inserted = (await connection.execute(insert)).one_or_none()
        if inserted is not None:
            return _from_row(inserted), True
        stored = (
            await connection.execute(
                sa.select(*_PUBLIC_COLUMNS).where(results.c.job_id == result.job_id)
            )
        ).one()
        return _from_row(stored), False


async def get(engine: AsyncEngine, job_id: UUID) -> AnalysisResult | None:
    async with _connect(engine) as connection:
        row = (
            await connection.execute(
                sa.select(*_PUBLIC_COLUMNS).where(results.c.job_id == job_id)
            )
        ).one_or_none()
    return None if row is None else _from_row(row)


async def newest_first(
    engine: AsyncEngine, limit: int, offset: int
) -> list[AnalysisResult]:
    query = (
        sa.select(*_PUBLIC_COLUMNS)
        .order_by(results.c.stored_at.desc(), results.c.job_id)
        .limit(limit)
        .offset(offset)
    )
    async with _connect(engine) as connection:
        rows = (await connection.execute(query)).all()
    return [_from_row(row) for row in rows]
