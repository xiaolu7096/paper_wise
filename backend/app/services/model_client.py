from typing import Any

import httpx

from app.api.errors import AppError
from app.services.model_settings import ActiveModelConfig


class ChatCompletionsClient:
    def __init__(
        self,
        config: ActiveModelConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport

    async def text(self, messages: list[dict[str, str]]) -> str:
        return await self._request(messages)

    async def vision(self, prompt: str, image: bytes, mime_type: str) -> str:
        import base64

        encoded = base64.b64encode(image).decode("ascii")
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                    },
                ],
            }
        ]
        return await self._request(messages)

    async def _request(self, messages: list[dict[str, Any]]) -> str:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=120.0
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as error:
            raise AppError(504, "MODEL_TIMEOUT", "Model request timed out") from error
        except httpx.RequestError as error:
            raise AppError(502, "MODEL_UNAVAILABLE", "Model service is unavailable") from error

        if response.status_code == 429:
            raise AppError(429, "MODEL_RATE_LIMITED", "Model service rate limited the request")
        if response.status_code in {408, 504}:
            raise AppError(504, "MODEL_TIMEOUT", "Model request timed out")
        if response.status_code in {400, 404, 422}:
            raise AppError(502, "MODEL_BAD_RESPONSE", "Model rejected the request")
        if response.status_code in {401, 403} or response.status_code >= 500:
            raise AppError(502, "MODEL_UNAVAILABLE", "Model service is unavailable")
        if not response.is_success:
            raise AppError(502, "MODEL_UNAVAILABLE", "Model service is unavailable")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise AppError(502, "MODEL_BAD_RESPONSE", "Model returned an invalid response") from error
        if not isinstance(content, str) or not content.strip():
            raise AppError(502, "MODEL_BAD_RESPONSE", "Model returned an invalid response")
        return content.strip()
