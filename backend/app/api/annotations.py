from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.api.papers import ERROR, PaperId
from app.api.schemas import Annotation, AnnotationCreate, AnnotationListResponse
from app.services.annotations import AnnotationService

router = APIRouter(prefix="/papers/{paper_id}/annotations", tags=["annotations"])


def service(request: Request) -> AnnotationService:
    return AnnotationService(request.app.state.database)


@router.get("", response_model=AnnotationListResponse, responses={404: ERROR, 422: ERROR})
async def list_annotations(request: Request, paper_id: PaperId) -> AnnotationListResponse:
    return AnnotationListResponse(
        items=await run_in_threadpool(service(request).list, paper_id)
    )


@router.post(
    "",
    response_model=Annotation,
    status_code=201,
    responses={404: ERROR, 422: ERROR},
)
async def create_annotation(
    request: Request, paper_id: PaperId, value: AnnotationCreate
) -> Annotation:
    return await run_in_threadpool(service(request).create, paper_id, value)


@router.delete(
    "/{annotation_id}", status_code=204, responses={404: ERROR, 422: ERROR}
)
async def delete_annotation(
    request: Request, paper_id: PaperId, annotation_id: UUID
) -> Response:
    await run_in_threadpool(service(request).delete, paper_id, str(annotation_id))
    return Response(status_code=204)
