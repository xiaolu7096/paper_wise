import io
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from app.api.errors import AppError
from app.api.schemas import ExplainRegionResponse
from app.db.database import Database
from app.services.model_client import ChatCompletionsClient
from app.services.model_settings import ActiveModelConfig, ModelSettingsService
from app.services.papers import PaperService, utc_now
from app.services.auth import LOCAL_USER_ID

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
ALLOWED_FORMATS = {"PNG": ("image/png", ".png"), "JPEG": ("image/jpeg", ".jpg")}


@dataclass(frozen=True)
class AssetFile:
    path: Path
    mime_type: str
    byte_size: int


class AssetService:
    def __init__(
        self,
        database: Database,
        data_dir: Path,
        model_settings: ModelSettingsService,
        client_factory: Callable[[ActiveModelConfig], ChatCompletionsClient],
        user_id: str = LOCAL_USER_ID,
    ) -> None:
        self.database = database
        self.data_dir = data_dir
        self.user_id = user_id
        self.papers = PaperService(database, data_dir, user_id)
        self.model_settings = model_settings
        self.client_factory = client_factory

    async def explain_region(
        self,
        paper_id: str,
        image_bytes: bytes,
        page: int,
        bbox: tuple[float, float, float, float],
        rotation: int,
        nearby_text: str,
        question: str,
    ) -> ExplainRegionResponse:
        paper = self.papers.get(paper_id)
        self.papers.file(paper_id)
        if page > paper.page_count:
            raise AppError(422, "PAGE_OUT_OF_RANGE", "Page is outside the paper")
        mime_type, suffix, width, height = self._inspect_image(image_bytes)
        config = self.model_settings.active("vision")
        if config is None:
            raise AppError(
                409, "VISION_MODEL_NOT_CONFIGURED", "Vision model is not configured"
            )
        prompt = (
            "Explain the selected paper region using the image as the primary evidence. "
            f"Page: {page}. User question: {question}\nNearby extracted text:\n{nearby_text}"
        )
        explanation = await self.client_factory(config).vision(
            prompt, image_bytes, mime_type
        )
        asset_id = str(uuid4())
        relative_path = (
            Path("papers") / paper_id / "users" / self.user_id / "regions" / f"{asset_id}{suffix}"
        )
        final_path = self.data_dir / relative_path
        temporary = self.data_dir / "tmp" / f"{asset_id}.image"
        temporary.parent.mkdir(parents=True, exist_ok=True)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(image_bytes)
        os.replace(temporary, final_path)
        try:
            with self.database.connect() as connection:
                connection.execute(
                    """INSERT INTO assets (
                           asset_id, paper_id, mime_type, relative_path,
                           byte_size, width, height, created_at, user_id
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        asset_id,
                        paper_id,
                        mime_type,
                        relative_path.as_posix(),
                        len(image_bytes),
                        width,
                        height,
                        utc_now(),
                        self.user_id,
                    ),
                )
        except BaseException:
            final_path.unlink(missing_ok=True)
            raise
        return ExplainRegionResponse(
            asset_id=asset_id,
            explanation=explanation,
            page=page,
            bbox=bbox,
            viewport_rotation=rotation,
            model=config.model,
        )

    def file(self, paper_id: str, asset_id: str) -> AssetFile:
        self.papers.get(paper_id)
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT mime_type, relative_path, byte_size FROM assets
                   WHERE paper_id = ? AND asset_id = ? AND user_id = ?""",
                (paper_id, asset_id, self.user_id),
            ).fetchone()
        if row is None:
            raise AppError(404, "ASSET_NOT_FOUND", "Asset not found")
        path = self.data_dir / row["relative_path"]
        if not path.is_file():
            raise AppError(410, "ASSET_FILE_MISSING", "Asset file is missing")
        return AssetFile(path, row["mime_type"], row["byte_size"])

    def cleanup_orphans(self) -> None:
        cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT asset_id, relative_path FROM assets a
                   WHERE a.created_at < ? AND NOT EXISTS (
                       SELECT 1 FROM annotations n
                       WHERE n.asset_id = a.asset_id AND n.user_id = a.user_id
                   )""",
                (cutoff,),
            ).fetchall()
            for row in rows:
                path = self.data_dir / row["relative_path"]
                if not path.is_file():
                    continue
                try:
                    path.unlink()
                except OSError:
                    continue
                connection.execute("DELETE FROM assets WHERE asset_id = ?", (row["asset_id"],))

    @staticmethod
    def parse_bbox(raw: str) -> tuple[float, float, float, float]:
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as error:
            raise AssetService._validation("body.bbox", "Invalid BBox JSON") from error
        if (
            not isinstance(value, list)
            or len(value) != 4
            or any(type(item) not in {int, float} for item in value)
        ):
            raise AssetService._validation("body.bbox", "BBox must contain four numbers")
        x0, y0, x1, y1 = (float(item) for item in value)
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise AssetService._validation("body.bbox", "BBox is outside the viewport")
        return x0, y0, x1, y1

    @staticmethod
    def _inspect_image(data: bytes) -> tuple[str, str, int, int]:
        if len(data) > MAX_IMAGE_BYTES:
            raise AppError(413, "IMAGE_TOO_LARGE", "Image exceeds the size limit")
        try:
            with Image.open(io.BytesIO(data)) as image:
                image_format = image.format
                width, height = image.size
                if image_format not in ALLOWED_FORMATS:
                    raise AppError(
                        415, "UNSUPPORTED_MEDIA_TYPE", "Only PNG and JPEG images are supported"
                    )
                if width * height > MAX_IMAGE_PIXELS:
                    raise AppError(413, "IMAGE_TOO_LARGE", "Decoded image has too many pixels")
                if not (16 <= width <= 4096 and 16 <= height <= 4096):
                    raise AppError(400, "INVALID_IMAGE", "Image dimensions are invalid")
                image.load()
        except AppError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as error:
            raise AppError(400, "INVALID_IMAGE", "Image cannot be decoded") from error
        mime_type, suffix = ALLOWED_FORMATS[image_format]
        return mime_type, suffix, width, height

    @staticmethod
    def _validation(path: str, reason: str) -> AppError:
        return AppError(
            422,
            "VALIDATION_ERROR",
            "Request validation failed",
            {"fields": [{"path": path, "reason": reason}]},
        )
