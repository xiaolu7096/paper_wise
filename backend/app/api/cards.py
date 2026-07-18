from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app.api.papers import ERROR, PaperId
from app.api.schemas import CardRequest, CardResponse
from app.services.cards import CardService
from app.services.model_settings import ModelSettingsService

router = APIRouter(prefix="/papers/{paper_id}/card", tags=["cards"])


def service(request: Request) -> CardService:
    return CardService(
        request.app.state.database,
        ModelSettingsService(request.app.state.settings),
        request.app.state.model_client_factory,
    )


@router.post(
    "",
    response_model=CardResponse,
    responses={404: ERROR, 409: ERROR, 422: ERROR, 429: ERROR, 502: ERROR, 504: ERROR},
)
async def generate_card(
    request: Request, paper_id: PaperId, value: CardRequest
) -> CardResponse:
    return await service(request).generate(paper_id, value.regenerate)


@router.get("", response_model=CardResponse, responses={404: ERROR, 422: ERROR})
async def get_card(request: Request, paper_id: PaperId) -> CardResponse:
    return await run_in_threadpool(service(request).get, paper_id)
