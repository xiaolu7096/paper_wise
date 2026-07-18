import asyncio
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import fitz
import numpy as np

from app.db.database import Database
from app.services.embeddings import Embedder
from app.services.papers import utc_now
from app.services.text_index import clean_text, search_terms

MAX_CHUNK_TOKENS = 700
TARGET_CHUNK_TOKENS = 600
OVERLAP_TOKENS = 80


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    page: int
    ordinal: int
    text: str
    token_count: int


class IngestPipeline:
    def __init__(self, database: Database, data_dir: Path, embedder: Embedder) -> None:
        self.database = database
        self.data_dir = data_dir
        self.embedder = embedder

    def recover_interrupted(self) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            with self.database.transaction(connection):
                paper_ids = [
                    row[0]
                    for row in connection.execute(
                        "SELECT paper_id FROM tasks WHERE status = 'running'"
                    )
                ]
                connection.execute(
                    """
                    UPDATE tasks SET status = 'queued', stage = 'queued', progress = 0,
                                     error = NULL, updated_at = ?
                    WHERE status = 'running'
                    """,
                    (now,),
                )
                if paper_ids:
                    placeholders = ",".join("?" for _ in paper_ids)
                    connection.execute(
                        f"""
                        UPDATE papers SET status = 'queued', stage = 'queued', error = NULL,
                                          updated_at = ?
                        WHERE paper_id IN ({placeholders}) AND status = 'processing'
                        """,
                        (now, *paper_ids),
                    )

    def process_next(self) -> bool:
        task = self._claim_next()
        if task is None:
            return False
        self._process(task["task_id"], task["paper_id"])
        return True

    def _claim_next(self) -> sqlite3.Row | None:
        now = utc_now()
        with self.database.connect() as connection:
            with self.database.transaction(connection):
                row = connection.execute(
                    """
                    SELECT task_id, paper_id FROM tasks
                    WHERE status = 'queued' ORDER BY created_at ASC, task_id ASC LIMIT 1
                    """
                ).fetchone()
                if row is None:
                    return None
                updated = connection.execute(
                    """
                    UPDATE tasks SET status = 'running', stage = 'extracting', progress = 5,
                                     error = NULL, updated_at = ?
                    WHERE task_id = ? AND status = 'queued'
                    """,
                    (now, row["task_id"]),
                ).rowcount
                if updated != 1:
                    return None
                connection.execute(
                    """
                    UPDATE papers SET status = 'processing', stage = 'extracting',
                                      error = NULL, updated_at = ? WHERE paper_id = ?
                    """,
                    (now, row["paper_id"]),
                )
                return row

    def _process(self, task_id: str, paper_id: str) -> None:
        try:
            pages = self._extract_pages(self._paper_path(paper_id))
            self._stage(task_id, paper_id, "chunking", 30)
            chunks = self._chunks(pages)
            if not chunks:
                raise ValueError("No extractable text found in PDF")
            self._stage(task_id, paper_id, "embedding", 55)
            vectors = self.embedder.encode_passages([chunk.text for chunk in chunks])
            if len(vectors) != len(chunks):
                raise ValueError("Embedding count does not match chunks")
            self._stage(task_id, paper_id, "indexing", 85)
            self._store(task_id, paper_id, chunks, vectors)
        except Exception as error:
            self._fail(task_id, paper_id, str(error)[:1000] or "Ingest failed")

    def _stage(self, task_id: str, paper_id: str, stage: str, progress: int) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            with self.database.transaction(connection):
                connection.execute(
                    "UPDATE tasks SET stage = ?, progress = ?, updated_at = ? WHERE task_id = ?",
                    (stage, progress, now, task_id),
                )
                connection.execute(
                    "UPDATE papers SET stage = ?, updated_at = ? WHERE paper_id = ?",
                    (stage, now, paper_id),
                )

    def _store(
        self, task_id: str, paper_id: str, chunks: list[Chunk], vectors: np.ndarray
    ) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            with self.database.transaction(connection):
                connection.execute("DELETE FROM chunks_fts WHERE paper_id = ?", (paper_id,))
                connection.execute("DELETE FROM chunks WHERE paper_id = ?", (paper_id,))
                for chunk, vector in zip(chunks, vectors, strict=True):
                    normalized = np.asarray(vector, dtype=np.float32)
                    norm = float(np.linalg.norm(normalized))
                    if not np.isfinite(norm) or norm == 0:
                        raise ValueError("Embedding contains an invalid vector")
                    normalized /= norm
                    connection.execute(
                        """
                        INSERT INTO chunks (
                            paper_id, chunk_id, page, ordinal, text, embedding, token_count
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            paper_id,
                            chunk.chunk_id,
                            chunk.page,
                            chunk.ordinal,
                            chunk.text,
                            normalized.astype("<f4").tobytes(),
                            chunk.token_count,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO chunks_fts (paper_id, chunk_id, search_terms)
                        VALUES (?, ?, ?)
                        """,
                        (paper_id, chunk.chunk_id, search_terms(chunk.text)),
                    )
                connection.execute(
                    """
                    UPDATE tasks SET status = 'succeeded', stage = 'completed', progress = 100,
                                     error = NULL, updated_at = ? WHERE task_id = ?
                    """,
                    (now, task_id),
                )
                connection.execute(
                    """
                    UPDATE papers SET status = 'ready', stage = 'completed', error = NULL,
                                      updated_at = ? WHERE paper_id = ?
                    """,
                    (now, paper_id),
                )

    def _fail(self, task_id: str, paper_id: str, message: str) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            with self.database.transaction(connection):
                connection.execute(
                    """
                    UPDATE tasks SET status = 'failed', error = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (message, now, task_id),
                )
                stage = connection.execute(
                    "SELECT stage FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone()[0]
                connection.execute(
                    """
                    UPDATE papers SET status = 'failed', stage = ?, error = ?, updated_at = ?
                    WHERE paper_id = ?
                    """,
                    (stage, message, now, paper_id),
                )

    def _paper_path(self, paper_id: str) -> Path:
        return self.data_dir / "papers" / paper_id / "original.pdf"

    def _extract_pages(self, path: Path) -> list[list[str]]:
        with fitz.open(path) as document:
            raw_pages: list[list[tuple[str, float, float]]] = []
            repeated_candidates: Counter[str] = Counter()
            for page in document:
                blocks: list[tuple[str, float, float]] = []
                height = page.rect.height
                for block in page.get_text("blocks", sort=True):
                    if len(block) < 7 or block[6] != 0:
                        continue
                    text = clean_text(str(block[4]))
                    if not text:
                        continue
                    y0, y1 = float(block[1]), float(block[3])
                    blocks.append((text, y0, y1))
                    if len(text) <= 120 and (y0 <= height * 0.12 or y1 >= height * 0.88):
                        repeated_candidates[text] += 1
                raw_pages.append(blocks)
            threshold = max(2, int(len(raw_pages) * 0.6 + 0.999))
            repeated = {
                text for text, count in repeated_candidates.items() if count >= threshold
            }
            return [
                [text for text, _y0, _y1 in blocks if text not in repeated]
                for blocks in raw_pages
            ]

    def _chunks(self, pages: list[list[str]]) -> list[Chunk]:
        result: list[Chunk] = []
        for page_number, paragraphs in enumerate(pages, start=1):
            texts = self._page_chunks(paragraphs)
            for ordinal, text in enumerate(texts, start=1):
                result.append(
                    Chunk(
                        chunk_id=f"{page_number}-{ordinal:02d}",
                        page=page_number,
                        ordinal=ordinal,
                        text=text,
                        token_count=self.embedder.token_count(text),
                    )
                )
        return result

    def _page_chunks(self, paragraphs: list[str]) -> list[str]:
        expanded: list[str] = []
        for paragraph in paragraphs:
            expanded.extend(self._split_long(paragraph))
        chunks: list[str] = []
        current: list[str] = []
        for paragraph in expanded:
            candidate = "\n\n".join([*current, paragraph])
            if current and self.embedder.token_count(candidate) > TARGET_CHUNK_TOKENS:
                chunks.append("\n\n".join(current))
                overlap: list[str] = []
                for previous in reversed(current):
                    overlap.insert(0, previous)
                    if self.embedder.token_count("\n\n".join(overlap)) >= OVERLAP_TOKENS:
                        break
                current = overlap
            current.append(paragraph)
        if current:
            chunks.append("\n\n".join(current))
        return [text for text in chunks if text.strip()]

    def _split_long(self, text: str) -> list[str]:
        if self.embedder.token_count(text) <= MAX_CHUNK_TOKENS:
            return [text]
        parts: list[str] = []
        remaining = text
        while remaining:
            low, high = 1, len(remaining)
            best = 1
            while low <= high:
                middle = (low + high) // 2
                if self.embedder.token_count(remaining[:middle]) <= MAX_CHUNK_TOKENS:
                    best = middle
                    low = middle + 1
                else:
                    high = middle - 1
            split = best
            if split < len(remaining):
                whitespace = remaining.rfind(" ", max(1, split // 2), split)
                if whitespace > 0:
                    split = whitespace
            part = remaining[:split].strip()
            if part:
                parts.append(part)
            remaining = remaining[split:].strip()
        return parts


class JobRunner:
    def __init__(self, pipeline: IngestPipeline, poll_seconds: float = 0.5) -> None:
        self.pipeline = pipeline
        self.poll_seconds = poll_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        await asyncio.to_thread(self.pipeline.recover_interrupted)
        self._task = asyncio.create_task(self._run(), name="paperwise-ingest-runner")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    async def _run(self) -> None:
        while not self._stop.is_set():
            processed = await asyncio.to_thread(self.pipeline.process_next)
            if not processed:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)
                except TimeoutError:
                    pass
