import json
import os
from dataclasses import dataclass
from uuid import uuid4

from app.api.errors import AppError
from app.api.schemas import ModelConfigInput, ModelStatus, SettingsStatus, SettingsUpdate
from app.core.config import Settings


@dataclass(frozen=True)
class ActiveModelConfig:
    base_url: str
    model: str
    api_key: str


class ModelSettingsService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = settings.user_settings_path

    def status(self) -> SettingsStatus:
        return SettingsStatus(
            text_model=self._status("text"),
            vision_model=self._status("vision"),
        )

    def update(self, value: SettingsUpdate) -> SettingsStatus:
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
        stored = self._stored().get(f"{kind}_model")
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
        stored = self._stored().get(f"{kind}_model")
        if not isinstance(stored, dict):
            return ModelStatus(configured=False, base_url=None, model=None, source=None)
        try:
            model = ModelConfigInput(**stored)
        except Exception:
            return ModelStatus(configured=False, base_url=None, model=None, source="user_config")
        return ModelStatus(
            configured=True,
            base_url=model.base_url,
            model=model.model,
            source="user_config",
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
