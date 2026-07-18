import asyncio

import httpx
import numpy as np
from fastapi import FastAPI

from app.api.errors import AppError
from app.core.config import Settings
from app.main import create_app

NOW = "2026-07-15T00:00:00Z"
PAPER_ID = "a" * 64


class FakeEmbedder:
    def token_count(self, text: str) -> int:
        return len(text.split())

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return np.ones((len(texts), 2), dtype=np.float32)

    def encode_query(self, text: str) -> np.ndarray:
        return np.asarray([1.0, 0.0], dtype=np.float32)


class FakeClient:
    def __init__(self, answer: str = "Answer [S1] [S7]", error: AppError | None = None) -> None:
        self.answer = answer
        self.error = error
        self.messages = None

    async def text(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        return self.answer


def make_app(tmp_path, *, configured: bool = True) -> tuple[FastAPI, FakeClient]:
    values = {}
    if configured:
        values = {
            "text_model_base_url": "https://model.example/v1",
            "text_model_name": "model",
            "text_model_api_key": "secret",
        }
    app = create_app(
        Settings(data_dir=tmp_path, user_settings_path=tmp_path / "settings.json", jobs_enabled=False, **values),
        embedder=FakeEmbedder(),
    )
    client = FakeClient()
    app.state.model_client_factory = lambda _config: client
    app.state.database.migrate()
    with app.state.database.connect() as connection:
        connection.execute(
            """
            INSERT INTO papers (
                paper_id, filename, page_count, status, stage, created_at, updated_at
            ) VALUES (?, 'paper.pdf', 1, 'ready', 'completed', ?, ?)
            """,
            (PAPER_ID, NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO chunks (
                paper_id, chunk_id, page, ordinal, text, embedding, token_count
            ) VALUES (?, '1-01', 1, 1, 'Exact source quote.', ?, 3)
            """,
            (PAPER_ID, np.asarray([1.0, 0.0], dtype="<f4").tobytes()),
        )
        connection.execute(
            "INSERT INTO chunks_fts (paper_id, chunk_id, search_terms) VALUES (?, '1-01', 'source')",
            (PAPER_ID,),
        )
    return app, client


def send(app: FastAPI, method: str, url: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return await client.request(method, url, **kwargs)

    return asyncio.run(request())


def test_chat_builds_server_citations_and_persists_message_pair(tmp_path) -> None:
    app, model = make_app(tmp_path)

    response = send(app, "POST", f"/api/papers/{PAPER_ID}/chat", json={"question": "method?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Answer [S1] [S7]"
    assert body["citations"] == [
        {"source_id": "S1", "page": 1, "chunk_id": "1-01", "quote": "Exact source quote."}
    ]
    assert "[S1] Page 1\nExact source quote." in model.messages[0]["content"]
    assert "Simplified Chinese (简体中文)" in model.messages[0]["content"]
    messages = send(app, "GET", f"/api/papers/{PAPER_ID}/messages")
    assert [item["role"] for item in messages.json()["items"]] == ["user", "assistant"]
    assert messages.json()["items"][0]["citations"] == []


def test_model_failure_does_not_persist_either_message(tmp_path) -> None:
    app, _model = make_app(tmp_path)
    app.state.model_client_factory = lambda _config: FakeClient(
        error=AppError(502, "MODEL_UNAVAILABLE", "unavailable")
    )

    response = send(app, "POST", f"/api/papers/{PAPER_ID}/chat", json={"question": "method?"})

    assert response.status_code == 502
    messages = send(app, "GET", f"/api/papers/{PAPER_ID}/messages")
    assert messages.json() == {"items": []}


def test_chat_requires_ready_paper_and_configured_model(tmp_path) -> None:
    app, _model = make_app(tmp_path, configured=False)
    no_model = send(app, "POST", f"/api/papers/{PAPER_ID}/chat", json={"question": "q"})
    assert no_model.status_code == 409
    assert no_model.json()["error"]["code"] == "TEXT_MODEL_NOT_CONFIGURED"

    with app.state.database.connect() as connection:
        connection.execute(
            "UPDATE papers SET status = 'queued', stage = 'queued' WHERE paper_id = ?",
            (PAPER_ID,),
        )
    not_ready = send(app, "POST", f"/api/papers/{PAPER_ID}/chat", json={"question": "q"})
    assert not_ready.status_code == 409
    assert not_ready.json()["error"]["code"] == "PAPER_NOT_READY"


def test_clear_messages_is_idempotent_and_paper_scoped(tmp_path) -> None:
    app, _model = make_app(tmp_path)
    send(app, "POST", f"/api/papers/{PAPER_ID}/chat", json={"question": "q"})

    first = send(app, "DELETE", f"/api/papers/{PAPER_ID}/messages")
    second = send(app, "DELETE", f"/api/papers/{PAPER_ID}/messages")

    assert first.status_code == 204
    assert second.status_code == 204
    assert send(app, "GET", f"/api/papers/{PAPER_ID}/messages").json() == {"items": []}
