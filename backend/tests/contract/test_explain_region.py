import asyncio
import io
from pathlib import Path

import httpx
from fastapi import FastAPI
from PIL import Image

from app.api.errors import AppError
from app.core.config import Settings
from app.main import create_app

PAPER_A = "a" * 64
PAPER_B = "b" * 64
NOW = "2026-07-15T00:00:00Z"


class FakeClient:
    def __init__(self) -> None:
        self.error = None
        self.call = None

    async def vision(self, prompt, image, mime_type):
        self.call = (prompt, image, mime_type)
        if self.error:
            raise self.error
        return "区域解释"


def image_bytes(format: str = "PNG", size=(20, 20)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, "white").save(output, format=format)
    return output.getvalue()


def make_app(tmp_path: Path, *, configured: bool = True):
    values = {}
    if configured:
        values = {
            "vision_model_base_url": "https://model.example/v1",
            "vision_model_name": "vision-model",
            "vision_model_api_key": "secret",
        }
    app = create_app(Settings(data_dir=tmp_path, user_settings_path=tmp_path / "settings.json", jobs_enabled=False, **values))
    model = FakeClient()
    app.state.model_client_factory = lambda _config: model
    app.state.database.migrate()
    with app.state.database.connect() as connection:
        for paper_id in (PAPER_A, PAPER_B):
            connection.execute(
                """INSERT INTO papers (paper_id, filename, page_count, status, stage, created_at, updated_at)
                   VALUES (?, 'paper.pdf', 2, 'queued', 'queued', ?, ?)""",
                (paper_id, NOW, NOW),
            )
            path = tmp_path / "papers" / paper_id / "original.pdf"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"%PDF-test")
    return app, model


def send(app: FastAPI, paper_id=PAPER_A, *, data=None, image=None) -> httpx.Response:
    fields = {
        "page": "1",
        "bbox": "[0.1,0.2,0.5,0.6]",
        "viewport_rotation": "90",
        "nearby_text": "nearby",
        "question": "what is this?",
    }
    fields.update(data or {})

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return await client.post(
                    f"/api/papers/{paper_id}/explain-region",
                    data=fields,
                    files={"image": ("crop.png", image if image is not None else image_bytes(), "application/octet-stream")},
                )
    return asyncio.run(request())


def test_region_uses_decoded_mime_persists_and_is_paper_scoped(tmp_path) -> None:
    app, model = make_app(tmp_path)
    response = send(app)
    assert response.status_code == 200
    body = response.json()
    assert body["bbox"] == [0.1, 0.2, 0.5, 0.6]
    assert body["viewport_rotation"] == 90
    assert model.call[2] == "image/png"

    async def get(paper_id):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            return await client.get(f"/api/papers/{paper_id}/assets/{body['asset_id']}")
    assert asyncio.run(get(PAPER_A)).headers["content-type"] == "image/png"
    assert asyncio.run(get(PAPER_B)).json()["error"]["code"] == "ASSET_NOT_FOUND"


def test_region_validation_and_failure_leave_no_asset(tmp_path) -> None:
    app, model = make_app(tmp_path)
    assert send(app, data={"page": "3"}).json()["error"]["code"] == "PAGE_OUT_OF_RANGE"
    assert send(app, data={"bbox": "[0.5,0,0.4,1]"}).status_code == 422
    assert send(app, image=b"not an image").json()["error"]["code"] == "INVALID_IMAGE"
    assert send(app, image=image_bytes("GIF")).json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert send(app, image=image_bytes(size=(10, 20))).json()["error"]["code"] == "INVALID_IMAGE"
    model.error = AppError(502, "MODEL_UNAVAILABLE", "unavailable")
    assert send(app).status_code == 502
    with app.state.database.connect() as connection:
        assert connection.execute("SELECT count(*) FROM assets").fetchone()[0] == 0
    assert not list((tmp_path / "papers" / PAPER_A / "regions").glob("*"))


def test_region_requires_only_vision_configuration(tmp_path) -> None:
    app, _ = make_app(tmp_path, configured=False)
    response = send(app)
    assert (response.status_code, response.json()["error"]["code"]) == (409, "VISION_MODEL_NOT_CONFIGURED")
