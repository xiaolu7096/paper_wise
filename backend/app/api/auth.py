from fastapi import APIRouter, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.api.papers import ERROR
from app.api.schemas import AuthUser, LoginRequest, RegisterRequest
from app.services.auth import SESSION_COOKIE, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def service(request: Request) -> AuthService:
    return AuthService(request.app.state.database, request.app.state.settings)


def set_session_cookie(request: Request, response: Response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        secure=request.app.state.settings.session_cookie_secure,
        samesite="lax",
        max_age=request.app.state.settings.session_days * 24 * 60 * 60,
        path="/",
    )


@router.post(
    "/register",
    response_model=AuthUser,
    status_code=201,
    responses={409: ERROR, 422: ERROR},
)
async def register(request: Request, value: RegisterRequest, response: Response) -> AuthUser:
    auth = service(request)
    actor = None
    if await run_in_threadpool(auth.has_real_user):
        actor = await run_in_threadpool(
            auth.user_for_session, request.cookies.get(SESSION_COOKIE)
        )
    user = await run_in_threadpool(auth.register, value.username, value.password, actor)
    if actor is None:
        session = await run_in_threadpool(service(request).create_session, user.user_id)
        set_session_cookie(request, response, session.session_id)
    return user


@router.post(
    "/login",
    response_model=AuthUser,
    responses={401: ERROR, 422: ERROR},
)
async def login(request: Request, value: LoginRequest, response: Response) -> AuthUser:
    user, session = await run_in_threadpool(
        service(request).login, value.username, value.password
    )
    set_session_cookie(request, response, session.session_id)
    return user


@router.post("/logout", status_code=204, responses={401: ERROR})
async def logout(request: Request) -> Response:
    await run_in_threadpool(
        service(request).logout, request.cookies.get(SESSION_COOKIE)
    )
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/me", response_model=AuthUser, responses={401: ERROR})
async def me(request: Request) -> AuthUser:
    return request.state.current_user
