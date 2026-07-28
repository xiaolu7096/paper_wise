import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.errors import AppError, error_response, register_exception_handlers
from app.api.routes import router
from app.api.schemas import AuthUser
from app.core.config import Settings
from app.db.database import Database
from app.jobs.ingest import IngestPipeline, JobRunner
from app.services.assets import AssetService
from app.services.embeddings import Embedder, SentenceTransformerEmbedder
from app.services.model_client import ChatCompletionsClient
from app.services.model_settings import ModelSettingsService
from app.services.papers import PaperService
from app.services.auth import LOCAL_USER_ID, SESSION_COOKIE, AuthService

logger = logging.getLogger("paperwise.requests")


def _request_id(value: str | None) -> str:
    if value:
        try:
            parsed = UUID(value)
            if parsed.version == 4:
                return str(parsed)
        except ValueError:
            pass
    return str(uuid4())


def create_app(
    settings: Settings | None = None, embedder: Embedder | None = None
) -> FastAPI:
    active_settings = settings or Settings()
    active_settings.validate_public_mode()
    database = Database(active_settings.data_dir / "paperwise.db")
    active_embedder = embedder or SentenceTransformerEmbedder(
        active_settings.embedding_model_name
    )
    runner = JobRunner(IngestPipeline(database, active_settings.data_dir, active_embedder))

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        active_settings.data_dir.mkdir(parents=True, exist_ok=True)
        database.migrate()
        PaperService(database, active_settings.data_dir).cleanup_pending_deletes()
        AssetService(
            database,
            active_settings.data_dir,
            ModelSettingsService(active_settings),
            ChatCompletionsClient,
        ).cleanup_orphans()
        if active_settings.jobs_enabled:
            await runner.start()
        try:
            yield
        finally:
            if active_settings.jobs_enabled:
                await runner.stop()

    app = FastAPI(
        title="PaperWise API",
        version="1.5.0",
        lifespan=lifespan,
    )
    app.state.settings = active_settings
    app.state.database = database
    app.state.job_runner = runner
    app.state.embedder = active_embedder
    app.state.model_client_factory = ChatCompletionsClient

    @app.middleware("http")
    async def request_context(request: Request, call_next) -> Response:
        request_id = _request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        started = perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        route = request.scope.get("route")
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "route": getattr(route, "path", request.url.path),
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
            },
        )
        return response

    @app.middleware("http")
    async def auth_context(request: Request, call_next) -> Response:
        if request.url.path.startswith("/api/") and request.url.path != "/api/health":
            is_auth_route = request.url.path.startswith("/api/auth/")
            auth_service = AuthService(database, active_settings)
            if active_settings.auth_enabled:
                if is_auth_route and request.url.path != "/api/auth/me":
                    pass
                else:
                    try:
                        user = auth_service.user_for_session(
                            request.cookies.get(SESSION_COOKIE)
                        )
                    except AppError as error:
                        return error_response(error)
                    request.state.current_user = user
                    request.state.user_id = user.user_id
            else:
                user = AuthUser(
                    user_id=LOCAL_USER_ID,
                    username="local",
                    role="admin",
                    created_at="1970-01-01T00:00:00Z",
                )
                request.state.current_user = user
                request.state.user_id = user.user_id
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[active_settings.frontend_origin],
        allow_methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"],
        allow_headers=["Content-Type", "Range", "X-Request-ID"],
        allow_credentials=True,
        expose_headers=[
            "Accept-Ranges",
            "Content-Length",
            "Content-Range",
            "X-Request-ID",
        ],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=active_settings.allowed_hosts)
    register_exception_handlers(app)
    app.include_router(router)
    return app


app = create_app()
