import sqlite3
from pathlib import Path
from uuid import uuid4

from app.api.errors import AppError
from app.api.schemas import RetryResponse, Task
from app.db.database import Database
from app.services.papers import utc_now


def task_from_row(row: sqlite3.Row) -> Task:
    return Task(**dict(row))


class TaskService:
    def __init__(self, database: Database, data_dir: Path) -> None:
        self.database = database
        self.data_dir = data_dir

    def get(self, task_id: str) -> Task:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT task_id, paper_id, kind, status, stage, progress,
                       error, created_at, updated_at
                FROM tasks WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            raise AppError(404, "TASK_NOT_FOUND", "Task not found")
        return task_from_row(row)

    def retry(self, paper_id: str) -> RetryResponse:
        now = utc_now()
        task_id = str(uuid4())
        with self.database.connect() as connection:
            with self.database.transaction(connection):
                paper = connection.execute(
                    "SELECT status FROM papers WHERE paper_id = ?", (paper_id,)
                ).fetchone()
                if paper is None:
                    raise AppError(404, "PAPER_NOT_FOUND", "Paper not found")
                if paper["status"] != "failed":
                    raise AppError(409, "PAPER_NOT_FAILED", "Paper is not in failed state")
                path = self.data_dir / "papers" / paper_id / "original.pdf"
                if not path.is_file():
                    raise AppError(410, "PAPER_FILE_MISSING", "The original PDF is missing")
                connection.execute(
                    """
                    INSERT INTO tasks (
                        task_id, paper_id, kind, status, stage, progress,
                        created_at, updated_at
                    ) VALUES (?, ?, 'ingest', 'queued', 'queued', 0, ?, ?)
                    """,
                    (task_id, paper_id, now, now),
                )
                connection.execute(
                    """
                    UPDATE papers SET status = 'queued', stage = 'queued', error = NULL,
                                      updated_at = ? WHERE paper_id = ?
                    """,
                    (now, paper_id),
                )
        return RetryResponse(paper_id=paper_id, task_id=task_id, status="queued")
