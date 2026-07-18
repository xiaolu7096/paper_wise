import errno
import hashlib
import os
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import fitz
from fastapi import UploadFile

from app.api.errors import AppError
from app.api.schemas import Paper, PaperUploadResponse
from app.db.database import Database

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
COPY_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class UploadOutcome:
    status_code: int
    response: PaperUploadResponse


@dataclass(frozen=True)
class PaperFile:
    path: Path
    filename: str
    size: int


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def paper_from_row(row: sqlite3.Row) -> Paper:
    return Paper(**dict(row))


class PaperService:
    def __init__(self, database: Database, data_dir: Path) -> None:
        self.database = database
        self.data_dir = data_dir

    def upload(self, uploaded: UploadFile) -> UploadOutcome:
        filename = self._filename(uploaded.filename)
        if not filename.lower().endswith(".pdf"):
            raise AppError(415, "UNSUPPORTED_MEDIA_TYPE", "Only .pdf files are supported")

        temporary = self.data_dir / "tmp" / f"{uuid4()}.upload"
        temporary.parent.mkdir(parents=True, exist_ok=True)
        try:
            paper_id, size = self._copy_and_hash(uploaded, temporary)
            with temporary.open("rb") as uploaded_file:
                signature = uploaded_file.read(5)
            if size < 5 or signature != b"%PDF-":
                raise AppError(400, "INVALID_PDF", "The uploaded file is not a valid PDF")
            try:
                with fitz.open(temporary) as document:
                    page_count = document.page_count
                    if page_count < 1:
                        raise AppError(400, "INVALID_PDF", "The PDF has no pages")
            except AppError:
                raise
            except Exception as error:
                raise AppError(400, "INVALID_PDF", "The uploaded file is not a valid PDF") from error

            existing = self.get_optional(paper_id)
            if existing:
                task_id = self._active_task_id(paper_id)
                status_code = 202 if existing.status in {"queued", "processing"} else 200
                return UploadOutcome(
                    status_code,
                    PaperUploadResponse(
                        paper=existing,
                        task_id=task_id if status_code == 202 else None,
                        deduplicated=True,
                    ),
                )

            now = utc_now()
            task_id = str(uuid4())
            final_path = self._paper_path(paper_id)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, final_path)
            try:
                with self.database.connect() as connection:
                    with self.database.transaction(connection):
                        connection.execute(
                            """
                            INSERT INTO papers (
                                paper_id, filename, page_count, status, stage,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, 'queued', 'queued', ?, ?)
                            """,
                            (paper_id, filename, page_count, now, now),
                        )
                        connection.execute(
                            """
                            INSERT INTO tasks (
                                task_id, paper_id, kind, status, stage, progress,
                                created_at, updated_at
                            ) VALUES (?, ?, 'ingest', 'queued', 'queued', 0, ?, ?)
                            """,
                            (task_id, paper_id, now, now),
                        )
            except BaseException:
                final_path.unlink(missing_ok=True)
                raise

            return UploadOutcome(
                202,
                PaperUploadResponse(
                    paper=self.get(paper_id), task_id=task_id, deduplicated=False
                ),
            )
        finally:
            temporary.unlink(missing_ok=True)

    def list(self) -> list[Paper]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT paper_id, filename, title, page_count, status, stage,
                       error, created_at, updated_at
                FROM papers
                ORDER BY updated_at DESC, paper_id ASC
                """
            ).fetchall()
        return [paper_from_row(row) for row in rows]

    def get_optional(self, paper_id: str) -> Paper | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT paper_id, filename, title, page_count, status, stage,
                       error, created_at, updated_at
                FROM papers WHERE paper_id = ?
                """,
                (paper_id,),
            ).fetchone()
        return paper_from_row(row) if row else None

    def get(self, paper_id: str) -> Paper:
        paper = self.get_optional(paper_id)
        if not paper:
            raise AppError(404, "PAPER_NOT_FOUND", "Paper not found")
        return paper

    def file(self, paper_id: str) -> PaperFile:
        paper = self.get(paper_id)
        path = self._paper_path(paper_id)
        if not path.is_file():
            raise AppError(410, "PAPER_FILE_MISSING", "The original PDF is missing")
        return PaperFile(path=path, filename=paper.filename, size=path.stat().st_size)

    def _active_task_id(self, paper_id: str) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT task_id FROM tasks
                WHERE paper_id = ? AND status IN ('queued', 'running')
                ORDER BY created_at DESC LIMIT 1
                """,
                (paper_id,),
            ).fetchone()
        return row[0] if row else None

    def _paper_path(self, paper_id: str) -> Path:
        return self.data_dir / "papers" / paper_id / "original.pdf"

    @staticmethod
    def _filename(raw: str | None) -> str:
        filename = (raw or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not filename or "\x00" in filename or len(filename) > 255:
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "Request validation failed",
                {"fields": [{"path": "body.file.filename", "reason": "Invalid filename"}]},
            )
        return filename

    @staticmethod
    def _copy_and_hash(uploaded: UploadFile, destination: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        total = 0
        uploaded.file.seek(0)
        try:
            with destination.open("xb") as target:
                while chunk := uploaded.file.read(COPY_CHUNK_BYTES):
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        raise AppError(413, "FILE_TOO_LARGE", "PDF exceeds the 200 MiB limit")
                    digest.update(chunk)
                    target.write(chunk)
        except OSError as error:
            if error.errno == errno.ENOSPC:
                raise AppError(507, "STORAGE_FULL", "Not enough local storage") from error
            raise
        return digest.hexdigest(), total


def content_disposition(filename: str) -> str:
    return f"inline; filename*=UTF-8''{quote(filename, safe='')}"


def file_chunks(path: Path, start: int, length: int) -> Iterator[bytes]:
    remaining = length
    with path.open("rb") as source:
        source.seek(start)
        while remaining:
            chunk = source.read(min(COPY_CHUNK_BYTES, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def parse_range(value: str | None, size: int) -> tuple[int, int, int]:
    if value is None:
        return 0, size - 1, 200
    if not value.startswith("bytes=") or "," in value:
        raise _range_error(size)
    bounds = value[6:].split("-", 1)
    if len(bounds) != 2:
        raise _range_error(size)
    first, last = bounds
    try:
        if first:
            start = int(first)
            end = int(last) if last else size - 1
        elif last:
            suffix = int(last)
            if suffix <= 0:
                raise ValueError
            start = max(size - suffix, 0)
            end = size - 1
        else:
            raise ValueError
    except ValueError as error:
        raise _range_error(size) from error
    if start < 0 or start >= size or end < start:
        raise _range_error(size)
    return start, min(end, size - 1), 206


def _range_error(size: int) -> AppError:
    return AppError(
        416,
        "RANGE_NOT_SATISFIABLE",
        "Requested byte range is not satisfiable",
        headers={"Content-Range": f"bytes */{size}"},
    )
