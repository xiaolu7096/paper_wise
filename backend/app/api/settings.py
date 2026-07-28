from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app.api.papers import ERROR
from app.api.schemas import SettingsStatus, SettingsUpdate
from app.services.model_settings import ModelSettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/status", response_model=SettingsStatus)
async def settings_status(request: Request) -> SettingsStatus:
    return await run_in_threadpool(
        ModelSettingsService(
            request.app.state.settings,
            request.app.state.database if request.app.state.settings.auth_enabled else None,
            getattr(request.state, "user_id", None) if request.app.state.settings.auth_enabled else None,
        ).status
    )


@router.put(
    "",
    response_model=SettingsStatus,
    responses={422: ERROR, 500: ERROR},
)
async def update_settings(request: Request, value: SettingsUpdate) -> SettingsStatus:
    service = ModelSettingsService(
        request.app.state.settings,
        request.app.state.database if request.app.state.settings.auth_enabled else None,
        getattr(request.state, "user_id", None) if request.app.state.settings.auth_enabled else None,
    )
    return await run_in_threadpool(service.update, value)
