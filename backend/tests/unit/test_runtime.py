import sqlite3


def test_sqlite_supports_fts5() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE probe USING fts5(content)")
        connection.execute("DROP TABLE probe")
    finally:
        connection.close()
