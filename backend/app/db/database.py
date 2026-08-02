import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self, connection: sqlite3.Connection) -> Iterator[None]:
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()

    def migrate(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                row[0] for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if migration.name in applied:
                    continue
                statements = self._statements(migration.read_text(encoding="utf-8"))
                foreign_keys_off = migration.name == "0002_opt005_users.sql"
                if foreign_keys_off:
                    connection.execute("PRAGMA foreign_keys=OFF")
                try:
                    with self.transaction(connection):
                        for statement in statements:
                            connection.execute(statement)
                        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
                        if violations:
                            raise sqlite3.IntegrityError(
                                f"Migration {migration.name} introduced foreign key violations"
                            )
                        connection.execute(
                            """
                            INSERT INTO schema_migrations (version, applied_at)
                            VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                            """,
                            (migration.name,),
                        )
                finally:
                    if foreign_keys_off:
                        connection.execute("PRAGMA foreign_keys=ON")

    @staticmethod
    def _statements(script: str) -> list[str]:
        statements: list[str] = []
        pending = ""
        for line in script.splitlines(keepends=True):
            pending += line
            if sqlite3.complete_statement(pending):
                statement = pending.strip()
                if statement:
                    statements.append(statement)
                pending = ""
        if pending.strip():
            raise ValueError("Incomplete SQL migration")
        return statements
