import json

import httpx
import pytest

from app.api.errors import AppError
from app.services.model_client import ChatCompletionsClient
from app.services.model_settings import ActiveModelConfig

CONFIG = ActiveModelConfig("https://model.example/v1", "test-model", "secret")


@pytest.mark.asyncio
async def test_text_client_sends_exact_non_streaming_contract() -> None:
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": " answer "}}]})

    client = ChatCompletionsClient(CONFIG, transport=httpx.MockTransport(handler))
    result = await client.text([{"role": "user", "content": "question"}])

    assert result == "answer"
    assert captured == {
        "url": "https://model.example/v1/chat/completions",
        "authorization": "Bearer secret",
        "body": {
            "model": "test-model",
            "messages": [{"role": "user", "content": "question"}],
            "temperature": 0.2,
            "stream": False,
        },
    }


@pytest.mark.asyncio
async def test_vision_client_uses_verified_mime_data_url() -> None:
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "image"}}]})

    client = ChatCompletionsClient(CONFIG, transport=httpx.MockTransport(handler))
    await client.vision("explain", b"png", "image/png")

    image_url = captured["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url == "data:image/png;base64,cG5n"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("upstream", "status", "code"),
    [
        (429, 429, "MODEL_RATE_LIMITED"),
        (400, 502, "MODEL_BAD_RESPONSE"),
        (401, 502, "MODEL_UNAVAILABLE"),
        (500, 502, "MODEL_UNAVAILABLE"),
        (504, 504, "MODEL_TIMEOUT"),
    ],
)
async def test_model_http_errors_are_mapped(upstream, status, code) -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(upstream))
    client = ChatCompletionsClient(CONFIG, transport=transport)

    with pytest.raises(AppError) as caught:
        await client.text([{"role": "user", "content": "question"}])

    assert caught.value.status_code == status
    assert caught.value.code == code


@pytest.mark.asyncio
async def test_invalid_success_response_is_rejected() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={"choices": []}))

    with pytest.raises(AppError) as caught:
        await ChatCompletionsClient(CONFIG, transport=transport).text([])

    assert caught.value.code == "MODEL_BAD_RESPONSE"
