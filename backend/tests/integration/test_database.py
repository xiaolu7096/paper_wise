import sqlite3

import pytest

from app.db.database import Database

PAPER_A = "a" * 64
PAPER_B = "b" * 64
NOW = "2026-07-15T00:00:00Z"


def insert_paper(connection: sqlite3.Connection, paper_id: str) -> None:
    connection.execute(
        """
        INSERT INTO papers (
            paper_id, filename, page_count, status, stage, created_at, updated_at
        ) VALUES (?, ?, 1, 'queued', 'queued', ?, ?)
        """,
        (paper_id, f"{paper_id[0]}.pdf", NOW, NOW),
    )


def test_migrations_are_idempotent_and_enable_required_pragmas(tmp_path) -> None:
    database = Database(tmp_path / "paperwise.db")
    database.migrate()
    database.migrate()

    with database.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
        assert {
            "schema_migrations",
            "papers",
            "tasks",
            "chunks",
            "chunks_fts",
            "messages",
            "cards",
            "assets",
            "annotations",
        } <= tables
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 2


def test_database_rejects_invalid_state_and_duplicate_active_task(tmp_path) -> None:
    database = Database(tmp_path / "paperwise.db")
    database.migrate()

    with database.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO papers (
                    paper_id, filename, page_count, status, created_at, updated_at
                ) VALUES (?, 'bad.pdf', 1, 'unknown', ?, ?)
                """,
                (PAPER_A, NOW, NOW),
            )

        insert_paper(connection, PAPER_A)
        task_values = (PAPER_A, NOW, NOW)
        connection.execute(
            """
            INSERT INTO tasks (
                task_id, paper_id, kind, status, stage, progress, created_at, updated_at
            ) VALUES ('11111111-1111-4111-8111-111111111111', ?, 'ingest',
                      'queued', 'queued', 0, ?, ?)
            """,
            task_values,
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, paper_id, kind, status, stage, progress, created_at, updated_at
                ) VALUES ('22222222-2222-4222-8222-222222222222', ?, 'ingest',
                          'running', 'extracting', 10, ?, ?)
                """,
                task_values,
            )


def test_asset_cannot_be_referenced_from_another_paper(tmp_path) -> None:
    database = Database(tmp_path / "paperwise.db")
    database.migrate()

    with database.connect() as connection:
        insert_paper(connection, PAPER_A)
        insert_paper(connection, PAPER_B)
        connection.execute(
            """
            INSERT INTO assets (
                asset_id, paper_id, mime_type, relative_path,
                byte_size, width, height, created_at
            ) VALUES ('33333333-3333-4333-8333-333333333333', ?, 'image/png',
                      'papers/a/regions/a.png', 100, 20, 20, ?)
            """,
            (PAPER_A, NOW),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO annotations (
                    annotation_id, paper_id, kind, page, bbox_json,
                    viewport_rotation, asset_id, ai_explanation, created_at, updated_at
                ) VALUES ('44444444-4444-4444-8444-444444444444', ?, 'region', 1,
                          '[0.1,0.1,0.2,0.2]', 0, '33333333-3333-4333-8333-333333333333',
                          'explanation', ?, ?)
                """,
                (PAPER_B, NOW, NOW),
            )


def test_chunk_and_fts_writes_roll_back_together(tmp_path) -> None:
    database = Database(tmp_path / "paperwise.db")
    database.migrate()

    with database.connect() as connection:
        insert_paper(connection, PAPER_A)
        connection.commit()
        with pytest.raises(RuntimeError):
            with database.transaction(connection):
                connection.execute(
                    """
                    INSERT INTO chunks (
                        paper_id, chunk_id, page, ordinal, text,
                        embedding, token_count
                    ) VALUES (?, '1-01', 1, 1, 'text', X'0000', 1)
                    """,
                    (PAPER_A,),
                )
                connection.execute(
                    """
                    INSERT INTO chunks_fts (paper_id, chunk_id, search_terms)
                    VALUES (?, '1-01', '测试')
                    """,
                    (PAPER_A,),
                )
                raise RuntimeError("force rollback")

        assert connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0] == 0
