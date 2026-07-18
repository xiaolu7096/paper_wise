from fastapi import APIRouter

from app.api.chat import router as chat_router
from app.api.cards import router as cards_router
from app.api.annotations import router as annotations_router
from app.api.explanations import router as explanations_router
from app.api.papers import router as papers_router
from app.api.schemas import HealthResponse
from app.api.settings import router as settings_router
from app.api.tasks import router as tasks_router

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version="1.2.0")


router.include_router(papers_router)
router.include_router(tasks_router)
router.include_router(settings_router)
router.include_router(chat_router)
router.include_router(explanations_router)
router.include_router(annotations_router)
router.include_router(cards_router)
