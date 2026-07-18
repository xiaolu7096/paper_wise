from io import BytesIO

import fitz
import numpy as np
from fastapi import UploadFile

from app.db.database import Database
from app.jobs.ingest import IngestPipeline
from app.services.papers import PaperService


class FakeEmbedder:
    def token_count(self, text: str) -> int:
        return max(1, len(text) // 4)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return np.asarray(
            [[float(index + 1), 1.0, 0.5] for index, _text in enumerate(texts)],
            dtype=np.float32,
        )

    def encode_query(self, text: str) -> np.ndarray:
        return np.asarray([1.0, 1.0, 0.5], dtype=np.float32)


def two_page_pdf() -> bytes:
    document = fitz.open()
    first = document.new_page()
    first.insert_text((72, 72), "First page method and experiment")
    second = document.new_page()
    second.insert_text((72, 72), "第二页 深度学习 结论")
    content = document.tobytes()
    document.close()
    return content


def setup_pipeline(tmp_path):
    database = Database(tmp_path / "paperwise.db")
    database.migrate()
    service = PaperService(database, tmp_path)
    upload = UploadFile(file=BytesIO(two_page_pdf()), filename="paper.pdf")
    outcome = service.upload(upload)
    pipeline = IngestPipeline(database, tmp_path, FakeEmbedder())
    return database, outcome, pipeline


def test_ingest_builds_page_scoped_chunks_fts_and_normalized_embeddings(tmp_path) -> None:
    database, outcome, pipeline = setup_pipeline(tmp_path)
    paper_id = outcome.response.paper.paper_id

    assert pipeline.process_next() is True

    with database.connect() as connection:
        paper = connection.execute(
            "SELECT status, stage FROM papers WHERE paper_id = ?", (paper_id,)
        ).fetchone()
        task = connection.execute(
            "SELECT status, stage, progress FROM tasks WHERE task_id = ?",
            (outcome.response.task_id,),
        ).fetchone()
        chunks = connection.execute(
            "SELECT chunk_id, page, embedding FROM chunks WHERE paper_id = ? ORDER BY page",
            (paper_id,),
        ).fetchall()
        fts = connection.execute(
            "SELECT search_terms FROM chunks_fts WHERE paper_id = ? ORDER BY chunk_id",
            (paper_id,),
        ).fetchall()

    assert tuple(paper) == ("ready", "completed")
    assert tuple(task) == ("succeeded", "completed", 100)
    assert [row["page"] for row in chunks] == [1, 2]
    assert [row["chunk_id"] for row in chunks] == ["1-01", "2-01"]
    for row in chunks:
        vector = np.frombuffer(row["embedding"], dtype="<f4")
        assert np.isclose(np.linalg.norm(vector), 1.0, atol=1e-6)
    assert "method" in fts[0]["search_terms"]
    assert pipeline.process_next() is False


def test_recovery_resets_running_task_and_processing_paper(tmp_path) -> None:
    database, outcome, pipeline = setup_pipeline(tmp_path)
    paper_id = outcome.response.paper.paper_id
    with database.connect() as connection:
        connection.execute(
            """
            UPDATE tasks SET status = 'running', stage = 'embedding', progress = 60
            WHERE task_id = ?
            """,
            (outcome.response.task_id,),
        )
        connection.execute(
            "UPDATE papers SET status = 'processing', stage = 'embedding' WHERE paper_id = ?",
            (paper_id,),
        )

    pipeline.recover_interrupted()

    with database.connect() as connection:
        task = connection.execute(
            "SELECT status, stage, progress FROM tasks WHERE task_id = ?",
            (outcome.response.task_id,),
        ).fetchone()
        paper = connection.execute(
            "SELECT status, stage FROM papers WHERE paper_id = ?", (paper_id,)
        ).fetchone()
    assert tuple(task) == ("queued", "queued", 0)
    assert tuple(paper) == ("queued", "queued")


def test_ingest_failure_records_stage_and_safe_error(tmp_path) -> None:
    database, outcome, pipeline = setup_pipeline(tmp_path)
    (tmp_path / "papers" / outcome.response.paper.paper_id / "original.pdf").unlink()

    assert pipeline.process_next() is True

    with database.connect() as connection:
        task = connection.execute(
            "SELECT status, stage, error FROM tasks WHERE task_id = ?",
            (outcome.response.task_id,),
        ).fetchone()
        paper = connection.execute(
            "SELECT status, stage, error FROM papers WHERE paper_id = ?",
            (outcome.response.paper.paper_id,),
        ).fetchone()
    assert task["status"] == "failed"
    assert task["stage"] == "extracting"
    assert task["error"]
    assert paper["status"] == "failed"
    assert paper["error"] == task["error"]
