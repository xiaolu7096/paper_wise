import asyncio

import httpx
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app


def make_app(tmp_path, **values) -> FastAPI:
    return create_app(
        Settings(
            data_dir=tmp_path / "data",
            user_settings_path=tmp_path / "config" / "settings.json",
            jobs_enabled=False,
            **values,
        )
    )


def send(app: FastAPI, method: str, url: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://localhost"
            ) as client:
                return await client.request(method, url, **kwargs)

    return asyncio.run(request())


def test_settings_update_is_atomic_and_never_echoes_keys(tmp_path) -> None:
    app = make_app(tmp_path)
    response = send(
        app,
        "PUT",
        "/api/settings",
        json={
            "text_model": {
                "base_url": "https://model.example/v1/",
                "model": "text-model",
                "api_key": "text-secret",
            },
            "vision_model": None,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "text_model": {
            "configured": True,
            "base_url": "https://model.example/v1",
            "model": "text-model",
            "source": "user_config",
        },
        "vision_model": {
            "configured": False,
            "base_url": None,
            "model": None,
            "source": None,
        },
    }
    assert "text-secret" not in response.text
    stored = (tmp_path / "config" / "settings.json").read_text(encoding="utf-8")
    assert "text-secret" in stored
    assert list((tmp_path / "config").glob("*.tmp")) == []


def test_environment_configuration_has_priority(tmp_path) -> None:
    app = make_app(
        tmp_path,
        text_model_base_url="https://environment.example/v1",
        text_model_name="environment-model",
        text_model_api_key="environment-secret",
    )
    send(
        app,
        "PUT",
        "/api/settings",
        json={
            "text_model": {
                "base_url": "https://stored.example/v1",
                "model": "stored-model",
                "api_key": "stored-secret",
            },
            "vision_model": None,
        },
    )

    status = send(app, "GET", "/api/settings/status")

    assert status.json()["text_model"] == {
        "configured": True,
        "base_url": "https://environment.example/v1",
        "model": "environment-model",
        "source": "environment",
    }


def test_settings_reject_url_credentials_query_and_extra_fields(tmp_path) -> None:
    response = send(
        make_app(tmp_path),
        "PUT",
        "/api/settings",
        json={
            "text_model": {
                "base_url": "https://user:pass@example.com/v1?x=1",
                "model": "model",
                "api_key": "key",
                "extra": True,
            },
            "vision_model": None,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
