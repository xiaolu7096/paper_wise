import asyncio
import hashlib
from io import BytesIO
from pathlib import Path

import fitz
import httpx
import pytest
from fastapi import FastAPI
from fastapi import UploadFile

from app.core.config import Settings
from app.main import create_app
from app.services.papers import COPY_CHUNK_BYTES, PaperService


def pdf_bytes(text: str = "PaperWise test paper") -> bytes:
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


def upload(app: FastAPI, content: bytes, filename: str = "paper.pdf") -> httpx.Response:
    return send(
        app,
        "POST",
        "/api/papers",
        files={"file": (filename, content, "application/pdf")},
    )


def test_upload_creates_paper_task_and_original_file(tmp_path) -> None:
    app = make_app(tmp_path)
    content = pdf_bytes()
    expected_id = hashlib.sha256(content).hexdigest()

    response = upload(app, content)

    assert response.status_code == 202
    body = response.json()
    assert body["deduplicated"] is False
    assert body["task_id"]
    assert body["paper"] == {
        "paper_id": expected_id,
        "filename": "paper.pdf",
        "title": None,
        "page_count": 1,
        "status": "queued",
        "stage": "queued",
        "error": None,
        "created_at": body["paper"]["created_at"],
        "updated_at": body["paper"]["updated_at"],
    }
    assert (tmp_path / "papers" / expected_id / "original.pdf").read_bytes() == content


def test_duplicate_upload_reuses_active_task_and_original_filename(tmp_path) -> None:
    app = make_app(tmp_path)
    content = pdf_bytes()
    first = upload(app, content, "first.pdf")
    second = upload(app, content, "second.pdf")

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["deduplicated"] is True
    assert second.json()["task_id"] == first.json()["task_id"]
    assert second.json()["paper"]["filename"] == "first.pdf"


def test_list_get_and_file_range_contract(tmp_path) -> None:
    app = make_app(tmp_path)
    content = pdf_bytes()
    paper_id = upload(app, content).json()["paper"]["paper_id"]

    listing = send(app, "GET", "/api/papers")
    detail = send(app, "GET", f"/api/papers/{paper_id}")
    complete = send(app, "GET", f"/api/papers/{paper_id}/file")
    partial = send(
        app,
        "GET",
        f"/api/papers/{paper_id}/file",
        headers={"Range": "bytes=0-9"},
    )
    head = send(app, "HEAD", f"/api/papers/{paper_id}/file", headers={"Range": "bytes=0-9"})

    assert listing.status_code == 200
    assert [item["paper_id"] for item in listing.json()["items"]] == [paper_id]
    assert detail.status_code == 200
    assert detail.json()["paper_id"] == paper_id
    assert complete.status_code == 200
    assert complete.content == content
    assert complete.headers["accept-ranges"] == "bytes"
    assert complete.headers["content-type"] == "application/pdf"
    assert partial.status_code == 206
    assert partial.content == content[:10]
    assert partial.headers["content-range"] == f"bytes 0-9/{len(content)}"
    assert head.status_code == 200
    assert head.content == b""
    assert int(head.headers["content-length"]) == len(content)


def test_invalid_range_uses_416_contract(tmp_path) -> None:
    app = make_app(tmp_path)
    content = pdf_bytes()
    paper_id = upload(app, content).json()["paper"]["paper_id"]

    response = send(
        app,
        "GET",
        f"/api/papers/{paper_id}/file",
        headers={"Range": f"bytes={len(content)}-"},
    )

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(content)}"
    assert response.json()["error"]["code"] == "RANGE_NOT_SATISFIABLE"


@pytest.mark.parametrize(
    ("filename", "content", "status", "code"),
    [
        ("paper.txt", b"%PDF-fake", 415, "UNSUPPORTED_MEDIA_TYPE"),
        ("paper.pdf", b"not a pdf", 400, "INVALID_PDF"),
    ],
)
def test_upload_rejects_invalid_files(tmp_path, filename, content, status, code) -> None:
    response = upload(make_app(tmp_path), content, filename)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_missing_paper_and_invalid_id_are_distinct(tmp_path) -> None:
    app = make_app(tmp_path)
    missing = send(app, "GET", f"/api/papers/{'c' * 64}")
    malformed = send(app, "GET", "/api/papers/not-a-sha256")

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PAPER_NOT_FOUND"
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "VALIDATION_ERROR"


def test_upload_enforces_streaming_size_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.services.papers.MAX_UPLOAD_BYTES", 10)

    response = upload(make_app(tmp_path), pdf_bytes())

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert list((tmp_path / "tmp").glob("*.upload")) == []


def test_missing_original_file_returns_410(tmp_path) -> None:
    app = make_app(tmp_path)
    paper_id = upload(app, pdf_bytes()).json()["paper"]["paper_id"]
    (tmp_path / "papers" / paper_id / "original.pdf").unlink()

    response = send(app, "GET", f"/api/papers/{paper_id}/file")

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "PAPER_FILE_MISSING"


@pytest.mark.parametrize("status", ["ready", "failed"])
def test_duplicate_terminal_paper_returns_200_without_task(tmp_path, status) -> None:
    app = make_app(tmp_path)
    content = pdf_bytes()
    first = upload(app, content)
    paper_id = first.json()["paper"]["paper_id"]
    with app.state.database.connect() as connection:
        connection.execute(
            "UPDATE papers SET status = ?, stage = ? WHERE paper_id = ?",
            (status, "completed" if status == "ready" else "embedding", paper_id),
        )
        connection.execute(
            """
            UPDATE tasks SET status = ?, stage = ?, progress = ? WHERE paper_id = ?
            """,
            (
                "succeeded" if status == "ready" else "failed",
                "completed" if status == "ready" else "embedding",
                100 if status == "ready" else 50,
                paper_id,
            ),
        )

    duplicate = upload(app, content)

    assert duplicate.status_code == 200
    assert duplicate.json()["deduplicated"] is True
    assert duplicate.json()["task_id"] is None
    assert duplicate.json()["paper"]["status"] == status


def test_suffix_and_malformed_ranges(tmp_path) -> None:
    app = make_app(tmp_path)
    content = pdf_bytes()
    paper_id = upload(app, content).json()["paper"]["paper_id"]

    suffix = send(
        app,
        "GET",
        f"/api/papers/{paper_id}/file",
        headers={"Range": "bytes=-8"},
    )
    malformed = send(
        app,
        "GET",
        f"/api/papers/{paper_id}/file",
        headers={"Range": "bytes=0-1,4-5"},
    )

    assert suffix.status_code == 206
    assert suffix.content == content[-8:]
    assert malformed.status_code == 416
    assert malformed.json()["error"]["code"] == "RANGE_NOT_SATISFIABLE"


def test_upload_copy_reads_bounded_chunks(tmp_path) -> None:
    class TrackingFile(BytesIO):
        def __init__(self, initial_bytes: bytes) -> None:
            super().__init__(initial_bytes)
            self.read_sizes: list[int] = []

        def read(self, size: int = -1) -> bytes:
            self.read_sizes.append(size)
            return super().read(size)

    content = b"x" * (COPY_CHUNK_BYTES + 10)
    tracking = TrackingFile(content)
    uploaded = UploadFile(file=tracking, filename="paper.pdf")
    destination = tmp_path / "copy.bin"

    digest, size = PaperService._copy_and_hash(uploaded, destination)

    assert size == len(content)
    assert digest == hashlib.sha256(content).hexdigest()
    assert tracking.read_sizes
    assert all(read_size == COPY_CHUNK_BYTES for read_size in tracking.read_sizes)


def test_paper_list_is_sorted_by_updated_at_descending(tmp_path) -> None:
    app = make_app(tmp_path)
    first_id = upload(app, pdf_bytes("first")).json()["paper"]["paper_id"]
    second_id = upload(app, pdf_bytes("second")).json()["paper"]["paper_id"]
    with app.state.database.connect() as connection:
        connection.execute(
            "UPDATE papers SET updated_at = '2026-01-01T00:00:00Z' WHERE paper_id = ?",
            (first_id,),
        )
        connection.execute(
            "UPDATE papers SET updated_at = '2026-01-02T00:00:00Z' WHERE paper_id = ?",
            (second_id,),
        )

    response = send(app, "GET", "/api/papers")

    assert [paper["paper_id"] for paper in response.json()["items"]] == [
        second_id,
        first_id,
    ]


def test_task_status_and_failed_paper_retry_contract(tmp_path) -> None:
    app = make_app(tmp_path)
    uploaded = upload(app, pdf_bytes()).json()
    task_id = uploaded["task_id"]
    paper_id = uploaded["paper"]["paper_id"]

    task = send(app, "GET", f"/api/tasks/{task_id}")
    assert task.status_code == 200
    assert task.json()["status"] == "queued"
    assert task.json()["stage"] == "queued"
    assert task.json()["progress"] == 0

    with app.state.database.connect() as connection:
        connection.execute(
            "UPDATE tasks SET status = 'failed', stage = 'embedding', error = 'failed' WHERE task_id = ?",
            (task_id,),
        )
        connection.execute(
            "UPDATE papers SET status = 'failed', stage = 'embedding', error = 'failed' WHERE paper_id = ?",
            (paper_id,),
        )

    retry = send(app, "POST", f"/api/papers/{paper_id}/retry")
    assert retry.status_code == 202
    assert retry.json()["paper_id"] == paper_id
    assert retry.json()["status"] == "queued"
    assert retry.json()["task_id"] != task_id


def test_retry_rejects_non_failed_paper(tmp_path) -> None:
    app = make_app(tmp_path)
    paper_id = upload(app, pdf_bytes()).json()["paper"]["paper_id"]

    response = send(app, "POST", f"/api/papers/{paper_id}/retry")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PAPER_NOT_FAILED"


def test_delete_paper_cascades_data_files_and_allows_reupload(tmp_path) -> None:
    app = make_app(tmp_path)
    content = pdf_bytes("delete me")
    uploaded = upload(app, content).json()
    paper_id = uploaded["paper"]["paper_id"]
    task_id = uploaded["task_id"]
    other_id = upload(app, pdf_bytes("keep me")).json()["paper"]["paper_id"]
    now = "2026-07-18T00:00:00Z"
    asset_id = "11111111-1111-4111-8111-111111111111"
    annotation_id = "22222222-2222-4222-8222-222222222222"
    message_id = "33333333-3333-4333-8333-333333333333"
    region = tmp_path / "papers" / paper_id / "regions" / f"{asset_id}.png"
    region.parent.mkdir(parents=True)
    region.write_bytes(b"region")
    with app.state.database.connect() as connection:
        connection.execute(
            "INSERT INTO chunks VALUES (?, '1-01', 1, 1, 'text', ?, 1)",
            (paper_id, b"\x00\x00\x80?"),
        )
        connection.execute(
            "INSERT INTO chunks_fts VALUES (?, '1-01', 'text')", (paper_id,)
        )
        connection.execute(
            "INSERT INTO messages VALUES (?, ?, 'user', 'question', NULL, ?)",
            (message_id, paper_id, now),
        )
        connection.execute(
            "INSERT INTO cards VALUES (?, '{}', 'model', ?)", (paper_id, now)
        )
        connection.execute(
            "INSERT INTO assets VALUES (?, ?, 'image/png', ?, 6, 16, 16, ?)",
            (asset_id, paper_id, region.relative_to(tmp_path).as_posix(), now),
        )
        connection.execute(
            """INSERT INTO annotations (
                   annotation_id, paper_id, kind, page, bbox_json,
                   viewport_rotation, selected_text, asset_id,
                   ai_explanation, note, created_at, updated_at
               ) VALUES (?, ?, 'region', 1, '[0.1,0.1,0.5,0.5]', 0, NULL, ?,
                         'explanation', NULL, ?, ?)""",
            (annotation_id, paper_id, asset_id, now, now),
        )

    response = send(app, "DELETE", f"/api/papers/{paper_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert not (tmp_path / "papers" / paper_id).exists()
    with app.state.database.connect() as connection:
        for table in (
            "papers", "tasks", "chunks", "messages", "cards", "assets", "annotations"
        ):
            assert connection.execute(
                f"SELECT count(*) FROM {table} WHERE paper_id = ?", (paper_id,)
            ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM chunks_fts WHERE paper_id = ?", (paper_id,)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM papers WHERE paper_id = ?", (other_id,)
        ).fetchone()[0] == 1
    assert send(app, "GET", f"/api/tasks/{task_id}").status_code == 404
    repeated = upload(app, content)
    assert repeated.status_code == 202
    assert repeated.json()["deduplicated"] is False


def test_delete_processing_paper_returns_busy_without_changes(tmp_path) -> None:
    app = make_app(tmp_path)
    uploaded = upload(app, pdf_bytes()).json()
    paper_id = uploaded["paper"]["paper_id"]
    with app.state.database.connect() as connection:
        connection.execute(
            "UPDATE papers SET status = 'processing', stage = 'extracting' WHERE paper_id = ?",
            (paper_id,),
        )
        connection.execute(
            "UPDATE tasks SET status = 'running', stage = 'extracting' WHERE paper_id = ?",
            (paper_id,),
        )

    response = send(app, "DELETE", f"/api/papers/{paper_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PAPER_BUSY"
    assert (tmp_path / "papers" / paper_id / "original.pdf").is_file()
    assert send(app, "GET", f"/api/papers/{paper_id}").status_code == 200


def test_delete_missing_directory_and_request_validation(tmp_path) -> None:
    app = make_app(tmp_path)
    paper_id = upload(app, pdf_bytes()).json()["paper"]["paper_id"]
    original = tmp_path / "papers" / paper_id / "original.pdf"
    original.unlink()
    original.parent.rmdir()

    nonempty = send(app, "DELETE", f"/api/papers/{paper_id}", content=b"{}")
    deleted = send(app, "DELETE", f"/api/papers/{paper_id}")
    repeated = send(app, "DELETE", f"/api/papers/{paper_id}")

    assert nonempty.status_code == 422
    assert nonempty.json()["error"]["code"] == "VALIDATION_ERROR"
    assert deleted.status_code == 204
    assert repeated.status_code == 404
    assert repeated.json()["error"]["code"] == "PAPER_NOT_FOUND"


def test_delete_atomic_move_failure_keeps_database_and_file(tmp_path, monkeypatch) -> None:
    app = make_app(tmp_path)
    paper_id = upload(app, pdf_bytes()).json()["paper"]["paper_id"]

    def deny_move(_source, _destination) -> None:
        raise PermissionError("busy")

    monkeypatch.setattr("app.services.papers.os.replace", deny_move)
    response = send(app, "DELETE", f"/api/papers/{paper_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PAPER_BUSY"
    assert (tmp_path / "papers" / paper_id / "original.pdf").is_file()
    assert send(app, "GET", f"/api/papers/{paper_id}").status_code == 200


def test_pending_delete_cleanup_only_removes_strictly_named_paths(tmp_path) -> None:
    pending = tmp_path / "tmp" / "paper-delete-11111111-1111-4111-8111-111111111111"
    pending.mkdir(parents=True)
    (pending / "original.pdf").write_bytes(b"pdf")
    unrelated = tmp_path / "tmp" / "keep.upload"
    unrelated.write_bytes(b"keep")

    PaperService(make_app(tmp_path).state.database, tmp_path).cleanup_pending_deletes()

    assert not pending.exists()
    assert unrelated.read_bytes() == b"keep"
