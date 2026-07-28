import base64
import hashlib
import hmac
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.api.errors import AppError
from app.api.schemas import AuthUser
from app.core.config import Settings
from app.db.database import Database

LOCAL_USER_ID = "00000000-0000-4000-8000-000000000000"
SESSION_COOKIE = "paperwise_session"
_PBKDF2_ITERATIONS = 200_000


@dataclass(frozen=True)
class SessionCookie:
    session_id: str
    expires_at: datetime


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class AuthService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    def register(
        self, username: str, password: str, actor: AuthUser | None = None
    ) -> AuthUser:
        now = utc_now()
        user_id = str(uuid4())
        has_real_user = self.has_real_user()
        if has_real_user and (actor is None or actor.role != "admin"):
            raise AppError(403, "FORBIDDEN", "Administrator privileges are required")
        role = "admin" if not has_real_user else "user"
        try:
            with self.database.connect() as connection:
                with self.database.transaction(connection):
                    connection.execute(
                        """
                        INSERT INTO users (user_id, username, password_hash, role, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (user_id, username, self._hash_password(password), role, now),
                    )
        except sqlite3.IntegrityError as error:
            raise AppError(409, "USER_ALREADY_EXISTS", "User already exists") from error
        return AuthUser(user_id=user_id, username=username, role=role, created_at=now)

    def login(self, username: str, password: str) -> tuple[AuthUser, SessionCookie]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT user_id, username, password_hash, role, created_at
                FROM users WHERE username = ? AND user_id != ?
                """,
                (username, LOCAL_USER_ID),
            ).fetchone()
        if row is None or not self._verify_password(password, row["password_hash"]):
            raise AppError(401, "INVALID_CREDENTIALS", "Invalid username or password")
        session = self.create_session(row["user_id"])
        return AuthUser(
            user_id=row["user_id"],
            username=row["username"],
            role=row["role"],
            created_at=row["created_at"],
        ), session

    def create_session(self, user_id: str) -> SessionCookie:
        now = datetime.now(UTC)
        expires = now + timedelta(days=self.settings.session_days)
        session_id = str(uuid4())
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (session_id, user_id, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    expires.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                    now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                ),
            )
        return SessionCookie(session_id=session_id, expires_at=expires)

    def user_for_session(self, session_id: str | None) -> AuthUser:
        if not session_id:
            raise AppError(401, "AUTH_REQUIRED", "Authentication is required")
        now = utc_now()
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT users.user_id, users.username, users.role, users.created_at
                FROM sessions
                JOIN users ON users.user_id = sessions.user_id
                WHERE sessions.session_id = ? AND sessions.expires_at > ?
                """,
                (session_id, now),
            ).fetchone()
        if row is None:
            raise AppError(401, "AUTH_REQUIRED", "Authentication is required")
        return AuthUser(**dict(row))

    def logout(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self.database.connect() as connection:
            connection.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def has_real_user(self) -> bool:
        with self.database.connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM users WHERE user_id != ? LIMIT 1", (LOCAL_USER_ID,)
                ).fetchone()
                is not None
            )

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
        )
        return (
            f"pbkdf2_sha256${_PBKDF2_ITERATIONS}$"
            f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"
        )

    @staticmethod
    def _verify_password(password: str, stored: str) -> bool:
        try:
            algorithm, iterations, salt, digest = stored.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            expected = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                base64.b64decode(salt),
                int(iterations),
            )
        except Exception:
            return False
        return hmac.compare_digest(expected, base64.b64decode(digest))
