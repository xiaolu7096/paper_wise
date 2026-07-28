from fastapi import APIRouter, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.api.papers import ERROR, PaperId
from app.api.schemas import ChatRequest, ChatResponse, MessageListResponse
from app.services.chat import ChatService
from app.services.model_settings import ModelSettingsService
from app.services.retrieval import RetrievalService

router = APIRouter(prefix="/papers/{paper_id}", tags=["chat"])


def service(request: Request) -> ChatService:
    user_id = getattr(request.state, "user_id", "00000000-0000-4000-8000-000000000000")
    return ChatService(
        request.app.state.database,
        RetrievalService(request.app.state.database, request.app.state.embedder),
        ModelSettingsService(
            request.app.state.settings,
            request.app.state.database if request.app.state.settings.auth_enabled else None,
            user_id if request.app.state.settings.auth_enabled else None,
        ),
        request.app.state.model_client_factory,
        user_id,
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={404: ERROR, 409: ERROR, 422: ERROR, 429: ERROR, 502: ERROR, 504: ERROR},
)
async def chat(request: Request, paper_id: PaperId, value: ChatRequest) -> ChatResponse:
    return await service(request).chat(paper_id, value.question)


@router.get("/messages", response_model=MessageListResponse, responses={404: ERROR, 422: ERROR})
async def messages(request: Request, paper_id: PaperId) -> MessageListResponse:
    items = await run_in_threadpool(service(request).messages, paper_id)
    return MessageListResponse(items=items)


@router.delete("/messages", status_code=204, responses={404: ERROR, 422: ERROR})
async def clear_messages(request: Request, paper_id: PaperId) -> Response:
    await run_in_threadpool(service(request).clear, paper_id)
    return Response(status_code=204)
