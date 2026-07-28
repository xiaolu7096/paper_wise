import math
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic import StringConstraints
from urllib.parse import urlsplit


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorField(StrictSchema):
    path: str
    reason: str


class ErrorDetails(StrictSchema):
    fields: list[ErrorField]


class ErrorBody(StrictSchema):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(StrictSchema):
    error: ErrorBody


class HealthResponse(StrictSchema):
    status: str
    version: str


class Paper(StrictSchema):
    paper_id: str
    filename: str
    title: str | None
    page_count: int
    status: Literal["queued", "processing", "ready", "failed"]
    stage: Literal[
        "queued", "extracting", "chunking", "embedding", "indexing", "completed"
    ] | None
    error: str | None
    created_at: str
    updated_at: str


class PaperUploadResponse(StrictSchema):
    paper: Paper
    task_id: str | None
    deduplicated: bool


class PaperListResponse(StrictSchema):
    items: list[Paper]


class Task(StrictSchema):
    task_id: str
    paper_id: str
    kind: Literal["ingest"]
    status: Literal["queued", "running", "succeeded", "failed"]
    stage: Literal[
        "queued", "extracting", "chunking", "embedding", "indexing", "completed"
    ]
    progress: int
    error: str | None
    created_at: str
    updated_at: str


class RetryResponse(StrictSchema):
    paper_id: str
    task_id: str
    status: Literal["queued"]


class AuthUser(StrictSchema):
    user_id: str
    username: str
    role: Literal["admin", "user"]
    created_at: str


class RegisterRequest(StrictSchema):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(RegisterRequest):
    pass


class ModelConfigInput(StrictSchema):
    base_url: str
    model: str = Field(min_length=1, max_length=200)
    api_key: str = Field(min_length=1, max_length=4096)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be an absolute HTTP(S) URL without credentials, query, or fragment")
        return value.rstrip("/")


class SettingsUpdate(StrictSchema):
    text_model: ModelConfigInput | None
    vision_model: ModelConfigInput | None


class ModelStatus(StrictSchema):
    configured: bool
    base_url: str | None
    model: str | None
    source: Literal["environment", "user_config", "user_encrypted"] | None


class SettingsStatus(StrictSchema):
    text_model: ModelStatus
    vision_model: ModelStatus


class ChatRequest(StrictSchema):
    question: str = Field(min_length=1, max_length=4000)


class Citation(StrictSchema):
    source_id: str
    page: int
    chunk_id: str
    quote: str = Field(min_length=1, max_length=800)


class ChatResponse(StrictSchema):
    user_message_id: str
    assistant_message_id: str
    answer: str
    citations: list[Citation]


class Message(StrictSchema):
    message_id: str
    role: Literal["user", "assistant"]
    content: str
    citations: list[Citation]
    created_at: str


class MessageListResponse(StrictSchema):
    items: list[Message]


class ExplainTextRequest(StrictSchema):
    page: int = Field(ge=1)
    selected_text: str = Field(min_length=1, max_length=12000)
    instruction: Literal["explain", "summarize", "question"]
    question: str | None
    context_before: str = Field(max_length=3000)
    context_after: str = Field(max_length=3000)

    @field_validator("selected_text", "context_before", "context_after", "question")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_question(self) -> "ExplainTextRequest":
        if not self.selected_text:
            raise ValueError("selected_text must not be empty")
        if self.instruction == "question":
            if not self.question or len(self.question) > 2000:
                raise ValueError("question must contain 1..2000 characters")
        elif self.question is not None:
            raise ValueError("question must be null unless instruction is question")
        return self


class ExplainTextResponse(StrictSchema):
    explanation: str
    page: int
    selected_text: str
    model: str


class ExplainRegionResponse(StrictSchema):
    asset_id: str
    explanation: str
    page: int
    bbox: tuple[float, float, float, float]
    viewport_rotation: Literal[0, 90, 180, 270]
    model: str


class AnnotationCreate(StrictSchema):
    kind: Literal["text", "region", "note"]
    page: int | None = Field(default=None, ge=1)
    bbox: tuple[float, float, float, float] | None = None
    viewport_rotation: Literal[0, 90, 180, 270] | None = None
    selected_text: str | None = Field(default=None, max_length=12000)
    asset_id: str | None = None
    ai_explanation: str | None = Field(default=None, max_length=30000)
    note: str | None = Field(default=None, max_length=20000)

    @field_validator("selected_text", "ai_explanation", "note")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        normalized = value.strip() if value is not None else None
        return normalized or None

    @field_validator("bbox")
    @classmethod
    def validate_bbox(
        cls, value: tuple[float, float, float, float] | None
    ) -> tuple[float, float, float, float] | None:
        if value is None:
            return None
        x0, y0, x1, y1 = value
        if not all(math.isfinite(item) for item in value) or not (
            0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1
        ):
            raise ValueError("bbox is outside the viewport")
        return value

    @field_validator("bbox", mode="before")
    @classmethod
    def reject_coerced_bbox(cls, value):
        if value is not None and (
            not isinstance(value, (list, tuple))
            or len(value) != 4
            or any(type(item) not in {int, float} for item in value)
        ):
            raise ValueError("bbox must contain four numbers")
        return value

    @field_validator("asset_id")
    @classmethod
    def validate_asset_id(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                UUID(value)
            except ValueError as error:
                raise ValueError("asset_id must be a UUID") from error
        return value

    @model_validator(mode="after")
    def validate_kind_fields(self) -> "AnnotationCreate":
        if self.kind == "text":
            valid = (
                self.page is not None
                and self.selected_text is not None
                and self.bbox is None
                and self.viewport_rotation is None
                and self.asset_id is None
                and (self.ai_explanation is not None or self.note is not None)
            )
        elif self.kind == "region":
            valid = (
                self.page is not None
                and self.bbox is not None
                and self.viewport_rotation is not None
                and self.asset_id is not None
                and self.selected_text is None
                and (self.ai_explanation is not None or self.note is not None)
            )
        else:
            valid = (
                self.note is not None
                and self.bbox is None
                and self.viewport_rotation is None
                and self.selected_text is None
                and self.asset_id is None
                and self.ai_explanation is None
            )
        if not valid:
            raise ValueError("fields do not match annotation kind")
        return self


class Annotation(AnnotationCreate):
    annotation_id: str
    paper_id: str
    created_at: str
    updated_at: str


class AnnotationListResponse(StrictSchema):
    items: list[Annotation]


CardText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class LegacyCard(StrictSchema):
    research_question: CardText
    method: CardText
    contributions: list[CardText] = Field(max_length=10)
    experiments: CardText
    findings: list[CardText] = Field(max_length=10)
    limitations: list[CardText] = Field(max_length=10)
    follow_up_questions: list[CardText] = Field(max_length=10)


class CardRequest(StrictSchema):
    regenerate: bool


class CardCitation(StrictSchema):
    source_id: str = Field(pattern=r"^S(?:[1-9]|1[0-2])$")
    page: int = Field(ge=1)
    chunk_id: str
    quote: str = Field(min_length=1, max_length=800)


class CardResponse(StrictSchema):
    schema_version: Literal[2]
    content_markdown: str = Field(min_length=1, max_length=60000)
    citations: list[CardCitation] = Field(max_length=12)
    model: str
    cached: bool
    updated_at: str
