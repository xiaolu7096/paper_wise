import asyncio
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI
from pydantic import ConfigDict

from app.api.errors import AppError
from app.api.schemas import StrictSchema
from app.core.config import Settings
from app.main import create_app


def make_app(tmp_path) -> FastAPI:
    settings = Settings(
        data_dir=tmp_path,
        frontend_origin="http://127.0.0.1:5173",
        jobs_enabled=False,
    )
    return create_app(settings)


def send(app: FastAPI, method: str, url: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://localhost"
            ) as client:
                return await client.request(method, url, **kwargs)

    return asyncio.run(request())


def test_health_contract(tmp_path) -> None:
    response = send(make_app(tmp_path), "GET", "/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.2.0"}
    UUID(response.headers["X-Request-ID"], version=4)


def test_valid_request_id_is_echoed(tmp_path) -> None:
    request_id = str(uuid4())
    response = send(
        make_app(tmp_path),
        "GET",
        "/api/health",
        headers={"X-Request-ID": request_id},
    )

    assert response.headers["X-Request-ID"] == request_id


def test_invalid_request_id_is_replaced(tmp_path) -> None:
    response = send(
        make_app(tmp_path),
        "GET",
        "/api/health",
        headers={"X-Request-ID": "not-a-uuid"},
    )

    assert response.headers["X-Request-ID"] != "not-a-uuid"
    UUID(response.headers["X-Request-ID"], version=4)


def test_validation_error_uses_contract_shape(tmp_path) -> None:
    class Payload(StrictSchema):
        model_config = ConfigDict(extra="forbid")
        value: str

    app = make_app(tmp_path)

    @app.post("/test-validation")
    async def test_validation(payload: Payload) -> dict[str, str]:
        return {"value": payload.value}

    response = send(
        app,
        "POST",
        "/test-validation",
        json={"value": "ok", "extra": True},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "Request validation failed"
    assert body["error"]["details"]["fields"] == [
        {"path": "body.extra", "reason": "Extra inputs are not permitted"}
    ]


def test_app_error_uses_contract_shape(tmp_path) -> None:
    app = make_app(tmp_path)

    @app.get("/test-error")
    async def test_error() -> None:
        raise AppError(409, "PAPER_NOT_READY", "Paper indexing is not complete")

    response = send(app, "GET", "/test-error")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "PAPER_NOT_READY",
            "message": "Paper indexing is not complete",
            "details": None,
        }
    }


def test_cors_only_allows_configured_origin(tmp_path) -> None:
    app = make_app(tmp_path)
    headers = {
        "Origin": "http://127.0.0.1:5173",
        "Access-Control-Request-Method": "GET",
    }
    allowed = send(app, "OPTIONS", "/api/health", headers=headers)
    denied = send(
        app,
        "OPTIONS",
        "/api/health",
        headers={**headers, "Origin": "https://example.com"},
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "access-control-allow-origin" not in denied.headers
