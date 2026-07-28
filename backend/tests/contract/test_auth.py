import asyncio
from pathlib import Path

import fitz
import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app


def pdf_bytes(text: str = "PaperWise private paper") -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def make_app(tmp_path: Path) -> FastAPI:
    return create_app(
        Settings(
            data_dir=tmp_path,
            frontend_origin="http://127.0.0.1:5173",
            jobs_enabled=False,
            auth_enabled=True,
            key_encryption_key=Fernet.generate_key().decode("utf-8"),
        )
    )


def send(
    app: FastAPI,
    method: str,
    url: str,
    cookies: httpx.Cookies | None = None,
    **kwargs,
) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://localhost",
                cookies=cookies,
            ) as client:
                return await client.request(method, url, **kwargs)

    return asyncio.run(request())


def register(
    app: FastAPI,
    username: str,
    password: str = "password-123",
    cookies: httpx.Cookies | None = None,
) -> httpx.Response:
    return send(
        app,
        "POST",
        "/api/auth/register",
        cookies=cookies,
        json={"username": username, "password": password},
    )


def login(
    app: FastAPI,
    username: str,
    password: str = "password-123",
) -> httpx.Response:
    return send(
        app,
        "POST",
        "/api/auth/login",
        json={"username": username, "password": password},
    )


def upload(app: FastAPI, cookies: httpx.Cookies, content: bytes) -> httpx.Response:
    return send(
        app,
        "POST",
        "/api/papers",
        cookies=cookies,
        files={"file": ("paper.pdf", content, "application/pdf")},
    )


def test_auth_required_and_admin_controlled_registration(tmp_path) -> None:
    app = make_app(tmp_path)

    anonymous = send(app, "GET", "/api/papers")
    admin = register(app, "admin")
    rejected = register(app, "stranger")
    created_user = register(app, "alice", cookies=admin.cookies)
    admin_me = send(app, "GET", "/api/auth/me", cookies=admin.cookies)
    logged_in = login(app, "alice")
    me = send(app, "GET", "/api/auth/me", cookies=logged_in.cookies)
    logout = send(app, "POST", "/api/auth/logout", cookies=logged_in.cookies)
    after_logout = send(app, "GET", "/api/auth/me", cookies=logged_in.cookies)

    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "AUTH_REQUIRED"
    assert admin.status_code == 201
    assert admin.json()["role"] == "admin"
    assert rejected.status_code == 401
    assert created_user.status_code == 201
    assert created_user.json()["role"] == "user"
    assert admin_me.json()["username"] == "admin"
    assert logged_in.status_code == 200
    assert me.json()["username"] == "alice"
    assert logout.status_code == 204
    assert after_logout.status_code == 401


def test_public_auth_mode_requires_key_encryption_key(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="PAPERWISE_KEY_ENCRYPTION_KEY"):
        create_app(
            Settings(
                data_dir=tmp_path,
                frontend_origin="http://127.0.0.1:5173",
                jobs_enabled=False,
                auth_enabled=True,
            )
        )


def test_public_host_requires_secure_cookie(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="PAPERWISE_SESSION_COOKIE_SECURE"):
        create_app(
            Settings(
                data_dir=tmp_path,
                frontend_origin="https://paperwise.example",
                jobs_enabled=False,
                auth_enabled=True,
                key_encryption_key=Fernet.generate_key().decode("utf-8"),
                public_host="paperwise.example",
                session_cookie_secure=False,
            )
        )


def test_user_model_settings_are_encrypted_and_isolated(tmp_path) -> None:
    app = make_app(tmp_path)
    admin = register(app, "admin")
    register(app, "bob", cookies=admin.cookies)
    user = login(app, "bob")

    response = send(
        app,
        "PUT",
        "/api/settings",
        cookies=user.cookies,
        json={
            "text_model": {
                "base_url": "https://model.example/v1",
                "model": "text-model",
                "api_key": "bob-secret",
            },
            "vision_model": None,
        },
    )
    admin_status = send(app, "GET", "/api/settings/status", cookies=admin.cookies)

    assert response.status_code == 200
    assert response.json()["text_model"]["source"] == "user_encrypted"
    assert "bob-secret" not in response.text
    assert admin_status.json()["text_model"]["configured"] is False
    with app.state.database.connect() as connection:
        stored = connection.execute(
            "SELECT encrypted_api_key FROM user_model_settings"
        ).fetchone()[0]
    assert "bob-secret" not in stored


def test_same_pdf_is_user_scoped_and_delete_does_not_cross_users(tmp_path) -> None:
    app = make_app(tmp_path)
    content = pdf_bytes()
    admin = register(app, "admin")
    register(app, "carol", cookies=admin.cookies)
    user = login(app, "carol")

    admin_upload = upload(app, admin.cookies, content)
    user_upload = upload(app, user.cookies, content)
    paper_id = admin_upload.json()["paper"]["paper_id"]

    assert admin_upload.status_code == 202
    assert user_upload.status_code == 202
    assert user_upload.json()["paper"]["paper_id"] == paper_id
    assert len(send(app, "GET", "/api/papers", cookies=admin.cookies).json()["items"]) == 1
    assert len(send(app, "GET", "/api/papers", cookies=user.cookies).json()["items"]) == 1

    deleted = send(app, "DELETE", f"/api/papers/{paper_id}", cookies=admin.cookies)

    assert deleted.status_code == 204
    assert send(app, "GET", f"/api/papers/{paper_id}", cookies=admin.cookies).status_code == 404
    assert send(app, "GET", f"/api/papers/{paper_id}", cookies=user.cookies).status_code == 200
    assert (tmp_path / "papers" / paper_id / "original.pdf").is_file()
