import json
import os
from dataclasses import dataclass
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

from app.api.errors import AppError
from app.api.schemas import ModelConfigInput, ModelStatus, SettingsStatus, SettingsUpdate
from app.core.config import Settings
from app.db.database import Database


@dataclass(frozen=True)
class ActiveModelConfig:
    base_url: str
    model: str
    api_key: str


class ModelSettingsService:
    def __init__(
        self, settings: Settings, database: Database | None = None, user_id: str | None = None
    ) -> None:
        self.settings = settings
        self.database = database
        self.user_id = user_id
        self.path = settings.user_settings_path

    def status(self) -> SettingsStatus:
        return SettingsStatus(
            text_model=self._status("text"),
            vision_model=self._status("vision"),
        )

    def update(self, value: SettingsUpdate) -> SettingsStatus:
        if self.database is not None and self.user_id is not None:
            return self._update_database(value)
        payload = {
            "text_model": value.text_model.model_dump() if value.text_model else None,
            "vision_model": value.vision_model.model_dump() if value.vision_model else None,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid4()}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            os.replace(temporary, self.path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise AppError(500, "SETTINGS_WRITE_FAILED", "Failed to write settings") from error
        return self.status()

    def active(self, kind: str) -> ActiveModelConfig | None:
        environment = self._environment(kind)
        if any(environment):
            if all(environment):
                return ActiveModelConfig(*environment)
            return None
        stored = self._database_config(kind) if self._uses_database() else self._stored().get(f"{kind}_model")
        if not isinstance(stored, dict):
            return None
        try:
            model = ModelConfigInput(**stored)
        except Exception:
            return None
        return ActiveModelConfig(model.base_url, model.model, model.api_key)

    def _status(self, kind: str) -> ModelStatus:
        environment = self._environment(kind)
        if any(environment):
            return ModelStatus(
                configured=all(environment),
                base_url=environment[0],
                model=environment[1],
                source="environment",
            )
        if self._uses_database():
            stored = self._database_config(kind, include_secret=False)
            source = "user_encrypted"
        else:
            stored = self._stored().get(f"{kind}_model")
            source = "user_config"
        if not isinstance(stored, dict):
            return ModelStatus(configured=False, base_url=None, model=None, source=None)
        try:
            if "api_key" in stored:
                model = ModelConfigInput(**stored)
                base_url = model.base_url
                model_name = model.model
            else:
                base_url = stored["base_url"]
                model_name = stored["model"]
        except Exception:
            return ModelStatus(configured=False, base_url=None, model=None, source=source)
        return ModelStatus(
            configured=True,
            base_url=base_url,
            model=model_name,
            source=source,
        )

    def _environment(self, kind: str) -> tuple[str | None, str | None, str | None]:
        return (
            getattr(self.settings, f"{kind}_model_base_url"),
            getattr(self.settings, f"{kind}_model_name"),
            getattr(self.settings, f"{kind}_model_api_key"),
        )

    def _stored(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _uses_database(self) -> bool:
        return self.database is not None and self.user_id is not None

    def _fernet(self) -> Fernet:
        if not self.settings.key_encryption_key:
            raise AppError(
                500,
                "SETTINGS_WRITE_FAILED",
                "Model key encryption key is not configured",
            )
        return Fernet(self.settings.key_encryption_key.encode("utf-8"))

    def _update_database(self, value: SettingsUpdate) -> SettingsStatus:
        assert self.database is not None
        assert self.user_id is not None
        now = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
        try:
            with self.database.connect() as connection:
                with self.database.transaction(connection):
                    for kind, model in (
                        ("text", value.text_model),
                        ("vision", value.vision_model),
                    ):
                        if model is None:
                            connection.execute(
                                "DELETE FROM user_model_settings WHERE user_id = ? AND kind = ?",
                                (self.user_id, kind),
                            )
                            continue
                        encrypted = self._fernet().encrypt(
                            model.api_key.encode("utf-8")
                        ).decode("utf-8")
                        connection.execute(
                            f"""
                            INSERT INTO user_model_settings (
                                user_id, kind, base_url, model, encrypted_api_key, updated_at
                            ) VALUES (?, ?, ?, ?, ?, {now})
                            ON CONFLICT(user_id, kind) DO UPDATE SET
                                base_url = excluded.base_url,
                                model = excluded.model,
                                encrypted_api_key = excluded.encrypted_api_key,
                                updated_at = excluded.updated_at
                            """,
                            (self.user_id, kind, model.base_url, model.model, encrypted),
                        )
        except AppError:
            raise
        except Exception as error:
            raise AppError(500, "SETTINGS_WRITE_FAILED", "Failed to write settings") from error
        return self.status()

    def _database_config(self, kind: str, include_secret: bool = True) -> dict | None:
        assert self.database is not None
        assert self.user_id is not None
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT base_url, model, encrypted_api_key
                FROM user_model_settings WHERE user_id = ? AND kind = ?
                """,
                (self.user_id, kind),
            ).fetchone()
        if row is None:
            return None
        result = {"base_url": row["base_url"], "model": row["model"]}
        if include_secret:
            try:
                result["api_key"] = self._fernet().decrypt(
                    row["encrypted_api_key"].encode("utf-8")
                ).decode("utf-8")
            except InvalidToken:
                return None
        return result
