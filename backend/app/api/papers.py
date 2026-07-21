from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import StringConstraints
from starlette.concurrency import run_in_threadpool

from app.api.errors import AppError
from app.api.schemas import (
    ErrorResponse,
    Paper,
    PaperListResponse,
    PaperUploadResponse,
    RetryResponse,
)
from app.services.papers import PaperService, content_disposition, file_chunks, parse_range
from app.services.tasks import TaskService

router = APIRouter(prefix="/papers", tags=["papers"])
PaperId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ERROR = {"model": ErrorResponse}
PDF_CONTENT = {
    "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}
}
HEAD_ERROR = {"description": "Error response without a body"}


def service(request: Request) -> PaperService:
    return PaperService(request.app.state.database, request.app.state.settings.data_dir)


@router.post(
    "",
    response_model=PaperUploadResponse,
    status_code=202,
    responses={
        200: {"model": PaperUploadResponse},
        400: ERROR,
        413: ERROR,
        415: ERROR,
        422: ERROR,
        507: ERROR,
    },
)
async def upload_paper(
    request: Request, file: Annotated[UploadFile, File()]
) -> JSONResponse:
    outcome = await run_in_threadpool(service(request).upload, file)
    return JSONResponse(
        status_code=outcome.status_code,
        content=outcome.response.model_dump(mode="json"),
    )


@router.get("", response_model=PaperListResponse)
async def list_papers(request: Request) -> PaperListResponse:
    papers = await run_in_threadpool(service(request).list)
    return PaperListResponse(items=papers)


@router.get("/{paper_id}", response_model=Paper, responses={404: ERROR, 422: ERROR})
async def get_paper(request: Request, paper_id: PaperId) -> Paper:
    return await run_in_threadpool(service(request).get, paper_id)


@router.delete(
    "/{paper_id}",
    status_code=204,
    responses={204: {"description": "Paper deleted"}, 404: ERROR, 409: ERROR, 422: ERROR, 500: ERROR},
)
async def delete_paper(request: Request, paper_id: PaperId) -> Response:
    if await request.body():
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Request validation failed",
            {"fields": [{"path": "body", "reason": "Request body must be empty"}]},
        )
    await run_in_threadpool(service(request).delete, paper_id)
    return Response(status_code=204)


@router.get(
    "/{paper_id}/file",
    responses={
        200: PDF_CONTENT,
        206: PDF_CONTENT,
        404: ERROR,
        410: ERROR,
        416: ERROR,
        422: ERROR,
    },
)
async def get_paper_file(request: Request, paper_id: PaperId) -> StreamingResponse:
    paper_file = await run_in_threadpool(service(request).file, paper_id)
    start, end, status_code = parse_range(request.headers.get("Range"), paper_file.size)
    length = end - start + 1
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Disposition": content_disposition(paper_file.filename),
    }
    if status_code == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{paper_file.size}"
    return StreamingResponse(
        file_chunks(paper_file.path, start, length),
        status_code=status_code,
        media_type="application/pdf",
        headers=headers,
    )


@router.head(
    "/{paper_id}/file",
    responses={200: PDF_CONTENT, 404: HEAD_ERROR, 410: HEAD_ERROR, 422: HEAD_ERROR},
)
async def head_paper_file(request: Request, paper_id: PaperId) -> Response:
    paper_file = await run_in_threadpool(service(request).file, paper_id)
    return Response(
        status_code=200,
        media_type="application/pdf",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(paper_file.size),
            "Content-Disposition": content_disposition(paper_file.filename),
        },
    )


@router.post(
    "/{paper_id}/retry",
    response_model=RetryResponse,
    status_code=202,
    responses={404: ERROR, 409: ERROR, 410: ERROR, 422: ERROR},
)
async def retry_paper(request: Request, paper_id: PaperId) -> RetryResponse:
    task_service = TaskService(
        request.app.state.database, request.app.state.settings.data_dir
    )
    return await run_in_threadpool(task_service.retry, paper_id)
