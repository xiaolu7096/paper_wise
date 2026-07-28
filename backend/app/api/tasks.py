from uuid import UUID

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app.api.papers import ERROR
from app.api.schemas import Task
from app.services.tasks import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=Task, responses={404: ERROR, 422: ERROR})
async def get_task(request: Request, task_id: UUID) -> Task:
    service = TaskService(
        request.app.state.database,
        request.app.state.settings.data_dir,
        getattr(request.state, "user_id", "00000000-0000-4000-8000-000000000000"),
    )
    return await run_in_threadpool(service.get, str(task_id))
