import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from app.api.errors import AppError
from app.api.schemas import CardCitation, CardResponse, LegacyCard
from app.db.database import Database
from app.services.model_client import ChatCompletionsClient
from app.services.model_settings import ActiveModelConfig, ModelSettingsService
from app.services.papers import utc_now

MAX_SOURCES = 12
MAX_CONTEXT_TOKENS = 12_000
MAX_CONTEXT_CHARS = 48_000
MAX_REPORT_CHARS = 60_000
SOURCE_PATTERN = re.compile(r"\[S(\d+)\]")


@dataclass(frozen=True)
class CardSource:
    source_id: str
    chunk_id: str
    page: int
    text: str


class CardService:
    def __init__(
        self,
        database: Database,
        model_settings: ModelSettingsService,
        client_factory: Callable[[ActiveModelConfig], ChatCompletionsClient],
    ) -> None:
        self.database = database
        self.model_settings = model_settings
        self.client_factory = client_factory

    def get(self, paper_id: str) -> CardResponse:
        self._paper_status(paper_id)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT content_json, model, updated_at FROM cards WHERE paper_id = ?",
                (paper_id,),
            ).fetchone()
        if row is None:
            raise AppError(404, "CARD_NOT_FOUND", "Card report not found")
        content = json.loads(row["content_json"])
        if isinstance(content, dict) and content.get("schema_version") == 2:
            return CardResponse(
                schema_version=2,
                content_markdown=content["content_markdown"],
                citations=content.get("citations", []),
                model=row["model"],
                cached=True,
                updated_at=row["updated_at"],
            )
        legacy = LegacyCard.model_validate(content)
        return CardResponse(
            schema_version=2,
            content_markdown=self._legacy_markdown(legacy),
            citations=[],
            model=row["model"],
            cached=True,
            updated_at=row["updated_at"],
        )

    async def generate(self, paper_id: str, regenerate: bool) -> CardResponse:
        status = self._paper_status(paper_id)
        if status != "ready":
            raise AppError(409, "PAPER_NOT_READY", "Paper indexing is not complete")
        if not regenerate:
            try:
                return self.get(paper_id)
            except AppError as error:
                if error.code != "CARD_NOT_FOUND":
                    raise
        config = self.model_settings.active("text")
        if config is None:
            raise AppError(
                409, "TEXT_MODEL_NOT_CONFIGURED", "Text model is not configured"
            )
        context, sources = self._context(paper_id)
        raw = await self.client_factory(config).text(
            [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": context},
            ]
        )
        markdown = self._normalize(raw)
        markdown, citations = self._citations(markdown, sources)
        updated_at = utc_now()
        stored = json.dumps(
            {
                "schema_version": 2,
                "content_markdown": markdown,
                "citations": [item.model_dump() for item in citations],
            },
            ensure_ascii=False,
        )
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO cards (paper_id, content_json, model, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(paper_id) DO UPDATE SET
                     content_json=excluded.content_json,
                     model=excluded.model,
                     updated_at=excluded.updated_at""",
                (paper_id, stored, config.model, updated_at),
            )
        return CardResponse(
            schema_version=2,
            content_markdown=markdown,
            citations=citations,
            model=config.model,
            cached=False,
            updated_at=updated_at,
        )

    def _paper_status(self, paper_id: str) -> str:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT status FROM papers WHERE paper_id = ?", (paper_id,)
            ).fetchone()
        if row is None:
            raise AppError(404, "PAPER_NOT_FOUND", "Paper not found")
        return row["status"]

    def _context(self, paper_id: str) -> tuple[str, dict[str, CardSource]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT chunk_id, page, text, token_count FROM chunks
                   WHERE paper_id = ? ORDER BY page ASC, ordinal ASC""",
                (paper_id,),
            ).fetchall()
        if len(rows) > MAX_SOURCES:
            indexes = sorted(
                {
                    round(index * (len(rows) - 1) / (MAX_SOURCES - 1))
                    for index in range(MAX_SOURCES)
                }
            )
            rows = [rows[index] for index in indexes]

        sources: dict[str, CardSource] = {}
        parts: list[str] = []
        characters = 0
        tokens = 0
        for row in rows:
            if sources and tokens + row["token_count"] > MAX_CONTEXT_TOKENS:
                continue
            source_id = f"S{len(sources) + 1}"
            header = f"[{source_id}] Page {row['page']}\n"
            available = MAX_CONTEXT_CHARS - characters - len(header)
            if available <= 0:
                break
            text = row["text"][:available]
            if not text:
                continue
            source = CardSource(
                source_id=source_id,
                chunk_id=row["chunk_id"],
                page=row["page"],
                text=row["text"],
            )
            sources[source_id] = source
            part = header + text
            parts.append(part)
            characters += len(part)
            tokens += row["token_count"]
        return "\n\n".join(parts), sources

    @staticmethod
    def _system_prompt() -> str:
        return (
            "仅依据提供的论文来源，生成一份简体中文 Markdown 速读报告。直接返回 "
            "Markdown，不要返回 JSON、代码围栏或原始 HTML。固定核心章节依次为："
            "# 论文速读、## 一句话总结、## 研究主题、## 关键结论、"
            "## 局限与适用边界、## 后续问题。根据论文实际类型，在关键结论与局限之间"
            "增加 2 至 6 个动态专业章节，例如方法设计、实验分析、分类体系、理论假设、"
            "数据构成或系统架构；不适用的章节不要强行生成。事实、结论和数字尽量使用"
            "所给的 [S1]..[S12] 标签引用来源，不得创造标签、页码、原文或论文未说明的"
            "事实。专有名词可以保留原文。"
        )

    @staticmethod
    def _normalize(raw: str) -> str:
        value = raw.strip()
        lines = value.splitlines()
        if (
            len(lines) >= 2
            and re.fullmatch(r"```(?:markdown|md)?\s*", lines[0], re.IGNORECASE)
            and lines[-1].strip() == "```"
        ):
            value = "\n".join(lines[1:-1]).strip()
        if not value or len(value) > MAX_REPORT_CHARS:
            raise AppError(
                502, "MODEL_BAD_RESPONSE", "Model returned an invalid report"
            )
        return value

    @staticmethod
    def _citations(
        markdown: str, sources: dict[str, CardSource]
    ) -> tuple[str, list[CardCitation]]:
        def validate(match: re.Match[str]) -> str:
            source_id = f"S{int(match.group(1))}"
            return f"[{source_id}]" if source_id in sources else ""

        cleaned = SOURCE_PATTERN.sub(validate, markdown)
        result: list[CardCitation] = []
        seen: set[str] = set()
        for number in SOURCE_PATTERN.findall(cleaned):
            source_id = f"S{int(number)}"
            if source_id in seen:
                continue
            seen.add(source_id)
            source = sources[source_id]
            result.append(
                CardCitation(
                    source_id=source_id,
                    page=source.page,
                    chunk_id=source.chunk_id,
                    quote=source.text[:800],
                )
            )
        return cleaned, result

    @staticmethod
    def _legacy_markdown(card: LegacyCard) -> str:
        def bullets(items: list[str]) -> str:
            return "\n".join(f"- {item}" for item in items) or "论文未说明。"

        return (
            "# 论文速读\n\n"
            "## 一句话总结\n"
            "此内容由旧版速读卡片确定性转换，请查看以下原有信息。\n\n"
            f"## 研究主题\n{card.research_question}\n\n"
            f"## 关键结论\n{bullets(card.findings)}\n\n"
            f"## 方法\n{card.method}\n\n"
            f"## 主要贡献\n{bullets(card.contributions)}\n\n"
            f"## 实验\n{card.experiments}\n\n"
            f"## 局限与适用边界\n{bullets(card.limitations)}\n\n"
            f"## 后续问题\n{bullets(card.follow_up_questions)}"
        )
