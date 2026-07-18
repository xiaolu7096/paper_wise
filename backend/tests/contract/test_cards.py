import asyncio
import json

import httpx
import numpy as np

from app.core.config import Settings
from app.main import create_app

PAPER_ID = "a" * 64
NOW = "2026-07-15T00:00:00Z"
REPORT = """# 论文速读

## 一句话总结
这是一篇测试论文。[S1] [S99]

## 研究主题
测试主题。

## 关键结论
- 结论。[S1]

## 方法设计
方法内容。

## 结果分析
结果内容。

## 局限与适用边界
论文未明确说明。

## 后续问题
- 后续问题。
"""
LEGACY_CARD = {
    "research_question": "旧研究问题",
    "method": "旧方法",
    "contributions": ["旧贡献"],
    "experiments": "旧实验",
    "findings": ["旧发现"],
    "limitations": [],
    "follow_up_questions": ["旧问题"],
}


class FakeClient:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0
        self.messages = []

    async def text(self, messages):
        self.calls += 1
        self.messages.append(messages)
        return self.answers.pop(0)


def make_app(tmp_path, answers=(REPORT,), *, ready=True, configured=True):
    values = {}
    if configured:
        values = {
            "text_model_base_url": "https://model/v1",
            "text_model_name": "model",
            "text_model_api_key": "key",
        }
    app = create_app(
        Settings(
            data_dir=tmp_path,
            user_settings_path=tmp_path / "settings.json",
            jobs_enabled=False,
            **values,
        )
    )
    model = FakeClient(answers)
    app.state.model_client_factory = lambda _config: model
    app.state.database.migrate()
    with app.state.database.connect() as connection:
        connection.execute(
            """INSERT INTO papers (
                   paper_id, filename, page_count, status, stage, created_at, updated_at
               ) VALUES (?, 'p.pdf', 3, ?, ?, ?, ?)""",
            (
                PAPER_ID,
                "ready" if ready else "queued",
                "completed" if ready else "queued",
                NOW,
                NOW,
            ),
        )
        if ready:
            for page in range(1, 4):
                connection.execute(
                    """INSERT INTO chunks (
                           paper_id, chunk_id, page, ordinal, text, embedding, token_count
                       ) VALUES (?, ?, ?, 1, ?, ?, 2)""",
                    (
                        PAPER_ID,
                        f"{page}-01",
                        page,
                        f"paper body page {page}",
                        np.ones(2, dtype="<f4").tobytes(),
                    ),
                )
    return app, model


def send(app, method="POST", body=None):
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://localhost"
            ) as client:
                return await client.request(
                    method, f"/api/papers/{PAPER_ID}/card", json=body
                )

    return asyncio.run(request())


def test_report_generates_once_validates_sources_and_uses_cache(tmp_path) -> None:
    app, model = make_app(tmp_path)

    first = send(app, body={"regenerate": False})
    cached = send(app, body={"regenerate": False})

    assert first.status_code == 200
    assert first.json()["schema_version"] == 2
    assert first.json()["cached"] is False
    assert "[S99]" not in first.json()["content_markdown"]
    assert first.json()["citations"] == [
        {
            "source_id": "S1",
            "page": 1,
            "chunk_id": "1-01",
            "quote": "paper body page 1",
        }
    ]
    assert cached.status_code == 200 and cached.json()["cached"] is True
    assert model.calls == 1
    prompt = model.messages[0][0]["content"]
    assert "简体中文" in prompt
    assert "动态专业章节" in prompt
    assert "[S1] Page 1" in model.messages[0][1]["content"]


def test_report_strips_outer_fence_without_a_repair_call(tmp_path) -> None:
    app, model = make_app(tmp_path, answers=(f"```markdown\n{REPORT}\n```",))

    response = send(app, body={"regenerate": True})

    assert response.status_code == 200
    assert response.json()["content_markdown"].startswith("# 论文速读")
    assert model.calls == 1


def test_invalid_report_does_not_overwrite_cache_or_retry(tmp_path) -> None:
    app, model = make_app(tmp_path, answers=(REPORT, "   "))
    original = send(app, body={"regenerate": False}).json()["content_markdown"]

    failed = send(app, body={"regenerate": True})

    assert (failed.status_code, failed.json()["error"]["code"]) == (
        502,
        "MODEL_BAD_RESPONSE",
    )
    assert model.calls == 2
    assert send(app, method="GET").json()["content_markdown"] == original


def test_legacy_cache_is_converted_without_calling_model(tmp_path) -> None:
    app, model = make_app(tmp_path)
    with app.state.database.connect() as connection:
        connection.execute(
            """INSERT INTO cards (paper_id, content_json, model, updated_at)
               VALUES (?, ?, 'legacy-model', ?)""",
            (PAPER_ID, json.dumps(LEGACY_CARD, ensure_ascii=False), NOW),
        )

    response = send(app, method="GET")

    assert response.status_code == 200
    assert response.json()["schema_version"] == 2
    assert "## 研究主题\n旧研究问题" in response.json()["content_markdown"]
    assert "## 方法\n旧方法" in response.json()["content_markdown"]
    assert response.json()["citations"] == []
    assert model.calls == 0


def test_report_ready_and_configuration_errors(tmp_path) -> None:
    queued, _ = make_app(tmp_path / "queued", ready=False)
    assert (
        send(queued, body={"regenerate": False}).json()["error"]["code"]
        == "PAPER_NOT_READY"
    )
    unconfigured, _ = make_app(tmp_path / "unconfigured", configured=False)
    assert (
        send(unconfigured, body={"regenerate": False}).json()["error"]["code"]
        == "TEXT_MODEL_NOT_CONFIGURED"
    )
