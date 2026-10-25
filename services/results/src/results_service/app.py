from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import create_async_engine

from results_service import store
from results_service.models import AnalysisResult
from results_service.settings import ResultsSettings


def create_app(settings: ResultsSettings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # The engine connects lazily, so startup never touches the database.
        app.state.engine = create_async_engine(settings.database_url)
        yield
        await app.state.engine.dispose()

    app = FastAPI(title="Results Service", lifespan=lifespan)

    @app.exception_handler(store.DatabaseUnavailable)
    async def database_unavailable(request: Request, exc: store.DatabaseUnavailable):
        return JSONResponse(
            {"detail": "Database unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.put("/results/{job_id}", response_model=AnalysisResult)
    async def put_result(
        job_id: UUID, result: AnalysisResult, request: Request, response: Response
    ):
        if result.job_id != job_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "job_id in the body differs from the path",
            )
        stored, inserted = await store.insert_first_write_wins(
            request.app.state.engine, result
        )
        response.status_code = (
            status.HTTP_201_CREATED if inserted else status.HTTP_200_OK
        )
        return stored

    @app.get("/results", response_model=list[AnalysisResult])
    async def list_results(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        return await store.newest_first(request.app.state.engine, limit, offset)

    @app.get("/results/{job_id}", response_model=AnalysisResult)
    async def get_result(job_id: UUID, request: Request):
        result = await store.get(request.app.state.engine, job_id)
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Result not found")
        return result

    return app
