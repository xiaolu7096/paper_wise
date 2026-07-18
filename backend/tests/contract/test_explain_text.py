import asyncio
from pathlib import Path

import httpx
from fastapi import FastAPI

from app.api.errors import AppError
from app.core.config import Settings
from app.main import create_app

PAPER_ID = "a" * 64
NOW = "2026-07-15T00:00:00Z"


class FakeClient:
    def __init__(self) -> None:
        self.error = None
        self.messages = None

    async def text(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        return "解释结果"


def make_app(tmp_path: Path, *, configured: bool = True, status: str = "queued"):
    values = {}
    if configured:
        values = {
            "text_model_base_url": "https://model.example/v1",
            "text_model_name": "text-model",
            "text_model_api_key": "secret",
        }
    app = create_app(
        Settings(data_dir=tmp_path, user_settings_path=tmp_path / "settings.json", jobs_enabled=False, **values)
    )
    model = FakeClient()
    app.state.model_client_factory = lambda _config: model
    app.state.database.migrate()
    with app.state.database.connect() as connection:
        connection.execute(
            """INSERT INTO papers (paper_id, filename, page_count, status, stage, created_at, updated_at)
               VALUES (?, 'paper.pdf', 2, ?, 'queued', ?, ?)""",
            (PAPER_ID, status, NOW, NOW),
        )
    path = tmp_path / "papers" / PAPER_ID / "original.pdf"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"%PDF-test")
    return app, model


def send(app: FastAPI, body: dict) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return await client.post(f"/api/papers/{PAPER_ID}/explain-text", json=body)
    return asyncio.run(request())


def body(**changes):
    value = {
        "page": 1,
        "selected_text": " selected ",
        "instruction": "explain",
        "question": None,
        "context_before": "before",
        "context_after": "after",
    }
    value.update(changes)
    return value


def test_explain_text_works_before_ready_and_has_no_persistence(tmp_path) -> None:
    app, model = make_app(tmp_path, status="failed")
    response = send(app, body())
    assert response.status_code == 200
    assert response.json() == {
        "explanation": "解释结果", "page": 1, "selected_text": "selected", "model": "text-model"
    }
    assert "Selection:\nselected" in model.messages[1]["content"]
    with app.state.database.connect() as connection:
        assert connection.execute("SELECT count(*) FROM annotations").fetchone()[0] == 0


def test_question_is_strictly_conditional(tmp_path) -> None:
    app, _ = make_app(tmp_path)
    assert send(app, body(instruction="question", question=None)).status_code == 422
    assert send(app, body(instruction="explain", question="why")).status_code == 422
    assert send(app, body(instruction="question", question="why")).status_code == 200


def test_page_and_configuration_and_model_errors(tmp_path) -> None:
    app, model = make_app(tmp_path)
    response = send(app, body(page=3))
    assert (response.status_code, response.json()["error"]["code"]) == (422, "PAGE_OUT_OF_RANGE")
    model.error = AppError(504, "MODEL_TIMEOUT", "timed out")
    assert send(app, body()).status_code == 504

    unconfigured, _ = make_app(tmp_path / "other", configured=False)
    response = send(unconfigured, body())
    assert (response.status_code, response.json()["error"]["code"]) == (409, "TEXT_MODEL_NOT_CONFIGURED")
