from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import StringConstraints

from app.api.papers import ERROR, PaperId
from app.api.schemas import ExplainRegionResponse, ExplainTextRequest, ExplainTextResponse
from app.services.assets import MAX_IMAGE_BYTES, AssetService
from app.services.explanations import ExplanationService
from app.services.model_settings import ModelSettingsService
from app.services.papers import PaperService

router = APIRouter(prefix="/papers/{paper_id}", tags=["explanations"])


def service(request: Request) -> ExplanationService:
    return ExplanationService(
        PaperService(request.app.state.database, request.app.state.settings.data_dir),
        ModelSettingsService(request.app.state.settings),
        request.app.state.model_client_factory,
    )


@router.post(
    "/explain-text",
    response_model=ExplainTextResponse,
    responses={404: ERROR, 409: ERROR, 422: ERROR, 429: ERROR, 502: ERROR, 504: ERROR},
)
async def explain_text(
    request: Request, paper_id: PaperId, value: ExplainTextRequest
) -> ExplainTextResponse:
    return await service(request).explain_text(paper_id, value)


def asset_service(request: Request) -> AssetService:
    return AssetService(
        request.app.state.database,
        request.app.state.settings.data_dir,
        ModelSettingsService(request.app.state.settings),
        request.app.state.model_client_factory,
    )


@router.post(
    "/explain-region",
    response_model=ExplainRegionResponse,
    responses={400: ERROR, 404: ERROR, 409: ERROR, 413: ERROR, 415: ERROR, 422: ERROR, 429: ERROR, 502: ERROR, 504: ERROR},
)
async def explain_region(
    request: Request,
    paper_id: PaperId,
    image: Annotated[UploadFile, File()],
    page: Annotated[int, Form(ge=1)],
    bbox: Annotated[str, Form()],
    viewport_rotation: Annotated[int, Form()],
    nearby_text: Annotated[str, Form(max_length=6000)],
    question: Annotated[str, Form(min_length=1, max_length=2000)],
) -> ExplainRegionResponse:
    if viewport_rotation not in {0, 90, 180, 270}:
        raise AssetService._validation("body.viewport_rotation", "Invalid viewport rotation")
    if not question.strip():
        raise AssetService._validation("body.question", "Question must not be empty")
    image_bytes = await image.read(MAX_IMAGE_BYTES + 1)
    return await asset_service(request).explain_region(
        paper_id,
        image_bytes,
        page,
        AssetService.parse_bbox(bbox),
        viewport_rotation,
        nearby_text.strip(),
        question.strip(),
    )


AssetId = Annotated[UUID, StringConstraints()]


@router.get(
    "/assets/{asset_id}",
    responses={200: {"content": {"image/png": {}, "image/jpeg": {}}}, 404: ERROR, 410: ERROR, 422: ERROR},
)
async def get_asset(
    request: Request, paper_id: PaperId, asset_id: AssetId
) -> FileResponse:
    asset = asset_service(request).file(paper_id, str(asset_id))
    return FileResponse(
        asset.path,
        media_type=asset.mime_type,
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
