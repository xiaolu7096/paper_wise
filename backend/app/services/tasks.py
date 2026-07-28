import sqlite3
from pathlib import Path
from uuid import uuid4

from app.api.errors import AppError
from app.api.schemas import RetryResponse, Task
from app.db.database import Database
from app.services.papers import utc_now
from app.services.auth import LOCAL_USER_ID


def task_from_row(row: sqlite3.Row) -> Task:
    return Task(**dict(row))


class TaskService:
    def __init__(
        self, database: Database, data_dir: Path, user_id: str = LOCAL_USER_ID
    ) -> None:
        self.database = database
        self.data_dir = data_dir
        self.user_id = user_id

    def get(self, task_id: str) -> Task:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT task_id, paper_id, kind, status, stage, progress,
                       error, created_at, updated_at
                FROM tasks WHERE task_id = ? AND user_id = ?
                """,
                (task_id, self.user_id),
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
                    """
                    SELECT status FROM papers
                    LEFT JOIN user_papers
                        ON user_papers.paper_id = papers.paper_id
                        AND user_papers.user_id = ?
                    WHERE papers.paper_id = ? AND (user_papers.user_id = ? OR ? = ?)
                    """,
                    (self.user_id, paper_id, self.user_id, self.user_id, LOCAL_USER_ID),
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
                        user_id, created_at, updated_at
                    ) VALUES (?, ?, 'ingest', 'queued', 'queued', 0, ?, ?, ?)
                    """,
                    (task_id, paper_id, self.user_id, now, now),
                )
                connection.execute(
                    """
                    UPDATE papers SET status = 'queued', stage = 'queued', error = NULL,
                                      updated_at = ? WHERE paper_id = ?
                    """,
                    (now, paper_id),
                )
        return RetryResponse(paper_id=paper_id, task_id=task_id, status="queued")
