import asyncio
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.api.errors import AppError
from app.api.schemas import ChatResponse, Citation, Message
from app.db.database import Database
from app.services.model_client import ChatCompletionsClient
from app.services.model_settings import ActiveModelConfig, ModelSettingsService
from app.services.retrieval import RetrievalService
from app.services.auth import LOCAL_USER_ID


class ChatService:
    def __init__(
        self,
        database: Database,
        retrieval: RetrievalService,
        model_settings: ModelSettingsService,
        client_factory: Callable[[ActiveModelConfig], ChatCompletionsClient],
        user_id: str = LOCAL_USER_ID,
    ) -> None:
        self.database = database
        self.retrieval = retrieval
        self.model_settings = model_settings
        self.client_factory = client_factory
        self.user_id = user_id

    async def chat(self, paper_id: str, question: str) -> ChatResponse:
        self._require_ready(paper_id)
        config = self.model_settings.active("text")
        if config is None:
            raise AppError(409, "TEXT_MODEL_NOT_CONFIGURED", "Text model is not configured")
        chunks = await asyncio.to_thread(self.retrieval.retrieve, paper_id, question)
        sources = {
            f"S{index}": chunk for index, chunk in enumerate(chunks, start=1)
        }
        source_text = "\n\n".join(
            f"[{source_id}] Page {chunk.page}\n{chunk.text}"
            for source_id, chunk in sources.items()
        ) or "No relevant source was found."
        recent = self._recent_messages(paper_id)
        messages = [
            {
                "role": "system",
                "content": (
                    "Answer only from the supplied paper sources. Cite claims with the exact "
                    "source labels [S1]..[S6]. Do not invent source labels, pages, or quotes. "
                    "If sources are insufficient, say so. Write the final answer in "
                    "Simplified Chinese (简体中文), while preserving proper nouns and source "
                    "labels.\n\nSources:\n" + source_text
                ),
            },
            *recent,
            {"role": "user", "content": question},
        ]
        answer = await self.client_factory(config).text(messages)
        citations = self._citations(answer, sources)
        user_id, assistant_id = str(uuid4()), str(uuid4())
        created = datetime.now(UTC)
        user_time = created.isoformat(timespec="microseconds").replace("+00:00", "Z")
        assistant_time = (created + timedelta(microseconds=1)).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z")
        with self.database.connect() as connection:
            with self.database.transaction(connection):
                connection.execute(
                    """
                    INSERT INTO messages (
                        message_id, paper_id, role, content, created_at, user_id
                    ) VALUES (?, ?, 'user', ?, ?, ?)
                    """,
                    (user_id, paper_id, question, user_time, self.user_id),
                )
                connection.execute(
                    """
                    INSERT INTO messages (
                        message_id, paper_id, role, content, citations_json, created_at, user_id
                    ) VALUES (?, ?, 'assistant', ?, ?, ?, ?)
                    """,
                    (
                        assistant_id,
                        paper_id,
                        answer,
                        json.dumps([item.model_dump() for item in citations], ensure_ascii=False),
                        assistant_time,
                        self.user_id,
                    ),
                )
        return ChatResponse(
            user_message_id=user_id,
            assistant_message_id=assistant_id,
            answer=answer,
            citations=citations,
        )

    def messages(self, paper_id: str) -> list[Message]:
        self._require_paper(paper_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT message_id, role, content, citations_json, created_at
                FROM messages WHERE paper_id = ? AND user_id = ?
                ORDER BY created_at ASC, message_id ASC
                """,
                (paper_id, self.user_id),
            ).fetchall()
        return [
            Message(
                message_id=row["message_id"],
                role=row["role"],
                content=row["content"],
                citations=json.loads(row["citations_json"]) if row["citations_json"] else [],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def clear(self, paper_id: str) -> None:
        self._require_paper(paper_id)
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM messages WHERE paper_id = ? AND user_id = ?",
                (paper_id, self.user_id),
            )

    def _require_paper(self, paper_id: str) -> None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM papers
                LEFT JOIN user_papers
                    ON user_papers.paper_id = papers.paper_id
                    AND user_papers.user_id = ?
                WHERE papers.paper_id = ? AND (user_papers.user_id = ? OR ? = ?)
                """,
                (self.user_id, paper_id, self.user_id, self.user_id, LOCAL_USER_ID),
            ).fetchone()
        if row is None:
            raise AppError(404, "PAPER_NOT_FOUND", "Paper not found")

    def _require_ready(self, paper_id: str) -> None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT status FROM papers
                LEFT JOIN user_papers
                    ON user_papers.paper_id = papers.paper_id
                    AND user_papers.user_id = ?
                WHERE papers.paper_id = ? AND (user_papers.user_id = ? OR ? = ?)
                """,
                (self.user_id, paper_id, self.user_id, self.user_id, LOCAL_USER_ID),
            ).fetchone()
        if row is None:
            raise AppError(404, "PAPER_NOT_FOUND", "Paper not found")
        if row["status"] != "ready":
            raise AppError(
                409,
                "PAPER_NOT_READY",
                "Paper indexing is not complete",
                {"paper_status": row["status"]},
            )

    def _recent_messages(self, paper_id: str) -> list[dict[str, str]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content FROM messages WHERE paper_id = ? AND user_id = ?
                ORDER BY created_at DESC, message_id DESC LIMIT 6
                """,
                (paper_id, self.user_id),
            ).fetchall()
        return [
            {"role": row["role"], "content": row["content"]}
            for row in reversed(rows)
        ]

    @staticmethod
    def _citations(answer: str, sources: dict) -> list[Citation]:
        result: list[Citation] = []
        seen: set[str] = set()
        for number in re.findall(r"\[S([1-6])\]", answer):
            source_id = f"S{number}"
            if source_id in seen or source_id not in sources:
                continue
            seen.add(source_id)
            chunk = sources[source_id]
            result.append(
                Citation(
                    source_id=source_id,
                    page=chunk.page,
                    chunk_id=chunk.chunk_id,
                    quote=chunk.text[:800],
                )
            )
        return result
