"""Results Service: stores Analysis Results and serves them and the UI.

Run with ``python -m results_service.main``.
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import create_async_engine

from results_service import store
from results_service.routes import router
from results_service.settings import ResultsSettings

PORT = 8000


def create_app(settings: ResultsSettings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # The engine connects lazily, so startup never touches the database.
        # pool_pre_ping swaps out pooled connections a database restart killed.
        app.state.engine = create_async_engine(
            settings.database_url, pool_pre_ping=True
        )
        yield
        await app.state.engine.dispose()

    app = FastAPI(title="Results Service", lifespan=lifespan)
    app.state.settings = settings

    @app.exception_handler(store.DatabaseUnavailable)
    async def database_unavailable(request: Request, exc: store.DatabaseUnavailable):
        return JSONResponse(
            {"detail": "Database unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    app.include_router(router)
    return app


def main() -> None:
    settings = ResultsSettings()
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",
        port=PORT,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
