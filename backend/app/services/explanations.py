from collections.abc import Callable

from app.api.errors import AppError
from app.api.schemas import ExplainTextRequest, ExplainTextResponse
from app.services.model_client import ChatCompletionsClient
from app.services.model_settings import ActiveModelConfig, ModelSettingsService
from app.services.papers import PaperService


class ExplanationService:
    def __init__(
        self,
        papers: PaperService,
        model_settings: ModelSettingsService,
        client_factory: Callable[[ActiveModelConfig], ChatCompletionsClient],
    ) -> None:
        self.papers = papers
        self.model_settings = model_settings
        self.client_factory = client_factory

    async def explain_text(
        self, paper_id: str, value: ExplainTextRequest
    ) -> ExplainTextResponse:
        paper = self.papers.get(paper_id)
        self.papers.file(paper_id)
        if value.page > paper.page_count:
            raise AppError(422, "PAGE_OUT_OF_RANGE", "Page is outside the paper")
        config = self.model_settings.active("text")
        if config is None:
            raise AppError(
                409, "TEXT_MODEL_NOT_CONFIGURED", "Text model is not configured"
            )
        action = {
            "explain": "Explain the selected passage clearly.",
            "summarize": "Summarize the selected passage concisely.",
            "question": f"Answer this question about the selected passage: {value.question}",
        }[value.instruction]
        explanation = await self.client_factory(config).text(
            [
                {
                    "role": "system",
                    "content": (
                        "Use only the supplied selection and local context. Do not claim facts "
                        "that are not present."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Page: {value.page}\nTask: {action}\n"
                        f"Context before:\n{value.context_before}\n\n"
                        f"Selection:\n{value.selected_text}\n\n"
                        f"Context after:\n{value.context_after}"
                    ),
                },
            ]
        )
        return ExplainTextResponse(
            explanation=explanation,
            page=value.page,
            selected_text=value.selected_text,
            model=config.model,
        )
