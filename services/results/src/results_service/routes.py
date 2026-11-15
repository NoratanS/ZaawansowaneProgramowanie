"""The Results Service's HTTP routes.

Handlers read ``settings`` and ``engine`` from ``request.app.state``, which
``create_app`` fills in.
"""

from importlib.resources import files
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse

from results_service import store
from results_service.auth import require_courier_token
from results_service.models import AnalysisResult

UI_FILES = files("results_service")
SINGLE_PAGE = UI_FILES.joinpath("index.html").read_text()
BATCH_PAGE = UI_FILES.joinpath("batch.html").read_text()
UI_SCRIPT = UI_FILES.joinpath("ui.js").read_text()
UI_STYLES = UI_FILES.joinpath("ui.css").read_text()

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
async def single_page():
    return SINGLE_PAGE


@router.get("/batch", response_class=HTMLResponse)
async def batch_page():
    return BATCH_PAGE


@router.get("/ui.js")
async def ui_script():
    return Response(UI_SCRIPT, media_type="text/javascript")


@router.get("/ui.css")
async def ui_styles():
    return Response(UI_STYLES, media_type="text/css")


@router.get("/ui-config")
async def ui_config(request: Request):
    return {"analysis_url": request.app.state.settings.analysis_public_url}


@router.put(
    "/results/{job_id}",
    response_model=AnalysisResult,
    dependencies=[Depends(require_courier_token())],
)
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
    response.status_code = status.HTTP_201_CREATED if inserted else status.HTTP_200_OK
    return stored


@router.get("/results", response_model=list[AnalysisResult])
async def list_results(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await store.newest_first(request.app.state.engine, limit, offset)


@router.get("/results/{job_id}", response_model=AnalysisResult)
async def get_result(job_id: UUID, request: Request):
    result = await store.get(request.app.state.engine, job_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Result not found")
    return result
