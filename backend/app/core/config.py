from pathlib import Path
import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from cryptography.fernet import Fernet

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_USER_SETTINGS = Path(
    os.environ.get("APPDATA", Path.home() / ".config")
) / "PaperWise" / "settings.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PAPERWISE_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    frontend_origin: str = "http://127.0.0.1:5173"
    data_dir: Path = PROJECT_ROOT / "data"
    jobs_enabled: bool = True
    auth_enabled: bool = False
    session_cookie_secure: bool = False
    session_days: int = Field(default=14, ge=1, le=90)
    secret_key: str | None = None
    key_encryption_key: str | None = None
    public_host: str | None = None
    embedding_model_name: str = "intfloat/multilingual-e5-small"
    user_settings_path: Path = DEFAULT_USER_SETTINGS
    text_model_base_url: str | None = None
    text_model_name: str | None = None
    text_model_api_key: str | None = None
    vision_model_base_url: str | None = None
    vision_model_name: str | None = None
    vision_model_api_key: str | None = None

    @property
    def allowed_hosts(self) -> list[str]:
        hosts = ["127.0.0.1", "localhost"]
        if self.public_host:
            hosts.append(self.public_host)
        return hosts

    def validate_public_mode(self) -> None:
        if self.public_host and not self.auth_enabled:
            raise RuntimeError("PAPERWISE_AUTH_ENABLED=true is required when PAPERWISE_PUBLIC_HOST is set")
        if self.public_host and not self.session_cookie_secure:
            raise RuntimeError(
                "PAPERWISE_SESSION_COOKIE_SECURE=true is required when PAPERWISE_PUBLIC_HOST is set"
            )
        if self.auth_enabled:
            if not self.key_encryption_key:
                raise RuntimeError("PAPERWISE_KEY_ENCRYPTION_KEY is required when auth is enabled")
            Fernet(self.key_encryption_key.encode("utf-8"))
