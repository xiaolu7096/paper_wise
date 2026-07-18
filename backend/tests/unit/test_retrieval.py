import sqlite3
from time import perf_counter

import numpy as np

from app.db.database import Database
from app.services.retrieval import RetrievalService, fts_match_query, rrf

NOW = "2026-07-15T00:00:00Z"


class FakeEmbedder:
    def token_count(self, text: str) -> int:
        return len(text.split())

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError

    def encode_query(self, text: str) -> np.ndarray:
        return np.asarray([1.0, 0.0], dtype=np.float32)


def insert_paper(connection: sqlite3.Connection, paper_id: str) -> None:
    connection.execute(
        """
        INSERT INTO papers (
            paper_id, filename, page_count, status, stage, created_at, updated_at
        ) VALUES (?, 'paper.pdf', 2, 'ready', 'completed', ?, ?)
        """,
        (paper_id, NOW, NOW),
    )


def insert_chunk(
    connection: sqlite3.Connection,
    paper_id: str,
    chunk_id: str,
    page: int,
    text: str,
    vector: tuple[float, float],
) -> None:
    ordinal = int(chunk_id.split("-")[1])
    connection.execute(
        """
        INSERT INTO chunks (
            paper_id, chunk_id, page, ordinal, text, embedding, token_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            paper_id,
            chunk_id,
            page,
            ordinal,
            text,
            np.asarray(vector, dtype="<f4").tobytes(),
            len(text.split()),
        ),
    )
    connection.execute(
        "INSERT INTO chunks_fts (paper_id, chunk_id, search_terms) VALUES (?, ?, ?)",
        (paper_id, chunk_id, text.lower()),
    )


def test_fts_query_is_generated_from_tokens_not_raw_syntax() -> None:
    assert fts_match_query('method" OR other:*') == '"method" OR "or" OR "other"'
    assert fts_match_query("深度学习") == '"深度" OR "度学" OR "学习"'
    assert fts_match_query("深") is None


def test_rrf_merges_and_deduplicates_stably() -> None:
    result = rrf([["a", "b"], ["b", "c"]])

    assert [item[0] for item in result] == ["b", "a", "c"]


def test_retrieval_is_isolated_by_paper_and_fuses_sparse_and_vector(tmp_path) -> None:
    database = Database(tmp_path / "paperwise.db")
    database.migrate()
    first, second = "a" * 64, "b" * 64
    with database.connect() as connection:
        insert_paper(connection, first)
        insert_paper(connection, second)
        insert_chunk(connection, first, "1-01", 1, "vector candidate", (1.0, 0.0))
        insert_chunk(connection, first, "2-01", 2, "method exact keyword", (0.0, 1.0))
        insert_chunk(connection, second, "1-01", 1, "method from another paper", (1.0, 0.0))

    results = RetrievalService(database, FakeEmbedder()).retrieve(first, "method")

    assert [item.chunk_id for item in results] == ["2-01", "1-01"]
    assert {item.page for item in results} == {1, 2}
    assert all("another paper" not in item.text for item in results)


def test_retrieval_returns_empty_for_paper_without_chunks(tmp_path) -> None:
    database = Database(tmp_path / "paperwise.db")
    database.migrate()
    with database.connect() as connection:
        insert_paper(connection, "a" * 64)

    assert RetrievalService(database, FakeEmbedder()).retrieve("a" * 64, "question") == []


def test_retrieval_compute_for_a_30_page_paper_is_under_200_ms(tmp_path) -> None:
    class RealisticEmbedder(FakeEmbedder):
        def encode_query(self, text: str) -> np.ndarray:
            vector = np.ones(384, dtype=np.float32)
            return vector / np.linalg.norm(vector)

    database = Database(tmp_path / "paperwise.db")
    database.migrate()
    paper_id = "c" * 64
    vector = np.ones(384, dtype="<f4")
    vector /= np.linalg.norm(vector)
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO papers (
                   paper_id, filename, page_count, status, stage, created_at, updated_at
               ) VALUES (?, 'paper.pdf', 30, 'ready', 'completed', ?, ?)""",
            (paper_id, NOW, NOW),
        )
        for page in range(1, 31):
            for ordinal in range(1, 11):
                chunk_id = f"{page}-{ordinal:02d}"
                text = f"method page {page} chunk {ordinal}"
                connection.execute(
                    """INSERT INTO chunks (
                           paper_id, chunk_id, page, ordinal, text, embedding, token_count
                       ) VALUES (?, ?, ?, ?, ?, ?, 5)""",
                    (paper_id, chunk_id, page, ordinal, text, vector.tobytes()),
                )
                connection.execute(
                    "INSERT INTO chunks_fts (paper_id, chunk_id, search_terms) VALUES (?, ?, ?)",
                    (paper_id, chunk_id, text),
                )

    started = perf_counter()
    results = RetrievalService(database, RealisticEmbedder()).retrieve(paper_id, "method")
    elapsed = perf_counter() - started

    assert len(results) == 6
    assert elapsed < 0.2
