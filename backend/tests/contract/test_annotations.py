import asyncio
from pathlib import Path

import httpx

from app.core.config import Settings
from app.main import create_app

PAPER_A = "a" * 64
PAPER_B = "b" * 64
ASSET_ID = "33333333-3333-4333-8333-333333333333"
NOW = "2026-07-15T00:00:00Z"


def make_app(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path, user_settings_path=tmp_path / "settings.json", jobs_enabled=False))
    app.state.database.migrate()
    with app.state.database.connect() as connection:
        for paper_id in (PAPER_A, PAPER_B):
            connection.execute(
                """INSERT INTO papers (paper_id, filename, page_count, status, stage, created_at, updated_at)
                   VALUES (?, 'p.pdf', 2, 'queued', 'queued', ?, ?)""",
                (paper_id, NOW, NOW),
            )
        connection.execute(
            """INSERT INTO assets (asset_id, paper_id, mime_type, relative_path, byte_size, width, height, created_at)
               VALUES (?, ?, 'image/png', 'a.png', 100, 20, 20, ?)""",
            (ASSET_ID, PAPER_A, NOW),
        )
    return app


def send(app, method, url, **kwargs):
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return await client.request(method, url, **kwargs)
    return asyncio.run(request())


def test_three_annotation_kinds_and_order_and_delete_isolation(tmp_path) -> None:
    app = make_app(tmp_path)
    values = [
        {"kind": "note", "note": "general"},
        {"kind": "text", "page": 2, "selected_text": "source", "ai_explanation": "explain"},
        {"kind": "region", "page": 1, "bbox": [0.1, 0.1, 0.5, 0.5], "viewport_rotation": 0, "asset_id": ASSET_ID, "note": "region"},
    ]
    created = [send(app, "POST", f"/api/papers/{PAPER_A}/annotations", json=value) for value in values]
    assert [response.status_code for response in created] == [201, 201, 201]
    items = send(app, "GET", f"/api/papers/{PAPER_A}/annotations").json()["items"]
    assert [item["kind"] for item in items] == ["region", "text", "note"]
    annotation_id = created[1].json()["annotation_id"]
    assert send(app, "DELETE", f"/api/papers/{PAPER_B}/annotations/{annotation_id}").status_code == 404
    assert send(app, "DELETE", f"/api/papers/{PAPER_A}/annotations/{annotation_id}").status_code == 204


def test_annotation_field_page_and_asset_validation(tmp_path) -> None:
    app = make_app(tmp_path)
    url = f"/api/papers/{PAPER_A}/annotations"
    invalid = [
        {"kind": "note", "note": ""},
        {"kind": "text", "page": 1, "selected_text": "x"},
        {"kind": "text", "page": 1, "selected_text": "x", "note": "n", "bbox": [0, 0, 1, 1]},
        {"kind": "region", "page": 1, "bbox": [0, 0, 1, 1], "viewport_rotation": 0, "asset_id": ASSET_ID, "selected_text": "x", "note": "n"},
    ]
    assert all(send(app, "POST", url, json=value).status_code == 422 for value in invalid)
    response = send(app, "POST", url, json={"kind": "note", "page": 3, "note": "n"})
    assert response.json()["error"]["code"] == "PAGE_OUT_OF_RANGE"
    response = send(app, "POST", f"/api/papers/{PAPER_B}/annotations", json={
        "kind": "region", "page": 1, "bbox": [0, 0, 1, 1], "viewport_rotation": 0,
        "asset_id": ASSET_ID, "note": "n",
    })
    assert response.json()["error"]["code"] == "ASSET_NOT_FOUND"
