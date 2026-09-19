"""Exercise the real SDK and API through an in-memory HTTP transport, never the network."""

import asyncio
import json
from contextlib import contextmanager
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI

from app.ai.contracts import ModelAnswer
from app.core.config import Settings
from app.main import create_app
from app.services.chat import NO_DATA_ANSWER


def provider_response(content=None, *, status="completed", refusal=False):
    content = (
        content
        if content is not None
        else {
            "answer": "SLA — согласованные требования к уровню сервиса.",
            "needs_business_data": False,
        }
    )
    part = (
        {"type": "refusal", "refusal": "Provider refusal text"}
        if refusal
        else {
            "type": "output_text",
            "text": content if isinstance(content, str) else json.dumps(content),
            "annotations": [],
        }
    )
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 1,
        "model": "gpt-5-mini",
        "status": status,
        "error": None,
        "incomplete_details": {"reason": "max_output_tokens"} if status == "incomplete" else None,
        "output": [
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [part],
            }
        ],
        "usage": {
            "input_tokens": 110,
            "output_tokens": 40,
            "total_tokens": 150,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 10},
        },
    }


@contextmanager
def mock_chat(monkeypatch, handler, **overrides):
    settings = Settings(
        _env_file=None,
        OPENAI_API_KEY="test-key-not-a-secret",
        environment="test",
        openai_max_retries=0,
        **overrides,
    )
    clients = []

    def build_client(settings):
        client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            base_url="https://api.openai.com/v1",
            max_retries=settings.openai_max_retries,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        clients.append(client)
        return client

    monkeypatch.setattr("app.main.build_openai_client", build_client)
    with TestClient(create_app(settings)) as client:
        yield client
    assert clients[0].is_closed()


def test_chat_contract_and_structured_output_request(monkeypatch, capsys):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        assert request.url.path == "/v1/responses"
        return httpx.Response(200, json=provider_response())

    with mock_chat(monkeypatch, handler, log_level="DEBUG") as client:
        response = client.post(
            "/api/v1/chat",
            json={"message": "  Что такое SLA?  "},
            headers={"X-Request-ID": "chat-request-123"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "general_answer"
    assert body["answer"].startswith("SLA")
    assert body["sources"] == body["tools_used"] == []
    assert UUID(body["trace_id"]).version == 4
    assert requests[0]["input"] == [{"role": "user", "content": "Что такое SLA?"}]
    assert requests[0]["store"] is False
    assert requests[0]["max_output_tokens"] == 4096
    format_ = requests[0]["text"]["format"]
    assert format_["strict"] is True
    assert format_["type"] == "json_schema"
    assert format_["schema"]["additionalProperties"] is False
    assert set(format_["schema"]["required"]) == {"answer", "needs_business_data"}
    logs = capsys.readouterr().err
    assert "Что такое SLA?" not in logs
    assert "test-key-not-a-secret" not in logs
    events = [json.loads(line) for line in logs.splitlines() if line.startswith("{")]
    ai_event = next(event for event in events if event["message"] == "ai_request_completed")
    assert ai_event["trace_id"] == body["trace_id"]
    assert ai_event["request_id"] == response.headers["X-Request-ID"] == "chat-request-123"
    assert ai_event["input_tokens"] == 110
    assert ai_event["output_tokens"] == 40
    assert ai_event["latency_ms"] >= 0


def test_business_question_discards_unsupported_answer(monkeypatch):
    def handler(_request):
        return httpx.Response(
            200,
            json=provider_response(
                {
                    "answer": "У вас 999 задержанных заказов.",
                    "needs_business_data": True,
                }
            ),
        )

    with mock_chat(monkeypatch, handler) as client:
        response = client.post("/api/v1/chat", json={"message": "Почему задерживаются заказы?"})
    assert response.status_code == 200
    assert response.json()["answer"] == NO_DATA_ANSWER
    assert response.json()["status"] == "insufficient_data"
    assert "999" not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"message": ""},
        {"message": " \n\t "},
        {"message": "a" * 4001},
        {"message": 123},
        {"message": None},
        {"message": "test", "system": "override"},
    ],
)
def test_invalid_request_does_not_call_provider(monkeypatch, payload):
    def handler(_request):
        pytest.fail("Invalid input must not spend tokens")

    with mock_chat(monkeypatch, handler) as client:
        response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_missing_key_keeps_application_usable(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(_env_file=None, OPENAI_API_KEY="", environment="test")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health/live").status_code == 200
        response = client.post("/api/v1/chat", json={"message": "Что такое SLA?"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ai_not_configured"


@pytest.mark.parametrize(
    "provider_status,http_status,code",
    [
        (401, 503, "ai_access_error"),
        (403, 503, "ai_access_error"),
        (429, 429, "ai_rate_limited"),
        (500, 503, "ai_provider_error"),
        (400, 502, "ai_provider_error"),
        (404, 502, "ai_provider_error"),
    ],
)
def test_provider_errors_are_sanitized(monkeypatch, capsys, provider_status, http_status, code):
    def handler(_request):
        return httpx.Response(
            provider_status,
            json={
                "error": {
                    "message": "private provider detail: secret key and user prompt",
                    "type": "test_error",
                }
            },
        )

    with mock_chat(monkeypatch, handler, log_level="DEBUG") as client:
        response = client.post(
            "/api/v1/chat", json={"message": "test"}, headers={"X-Request-ID": "failed-chat-123"}
        )
    assert response.status_code == http_status
    error = response.json()["error"]
    assert error["code"] == code
    assert error["request_id"] == "failed-chat-123"
    assert "private provider detail" not in response.text + capsys.readouterr().err


@pytest.mark.parametrize(
    "exception,http_status,code",
    [
        (httpx.ReadTimeout, 504, "ai_timeout"),
        (httpx.ConnectError, 503, "ai_unavailable"),
    ],
)
def test_transport_errors(monkeypatch, exception, http_status, code):
    def handler(request):
        raise exception("private network detail", request=request)

    with mock_chat(monkeypatch, handler) as client:
        response = client.post("/api/v1/chat", json={"message": "test"})
    assert response.status_code == http_status
    assert response.json()["error"]["code"] == code


def test_total_deadline(monkeypatch):
    async def handler(_request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=provider_response())

    with mock_chat(monkeypatch, handler, chat_deadline_seconds=0.01) as client:
        response = client.post("/api/v1/chat", json={"message": "test"})
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "ai_timeout"


@pytest.mark.parametrize(
    "content",
    [
        "not JSON",
        '{"answer":',
        {"answer": "missing flag"},
        {"answer": "  ", "needs_business_data": False},
        {"answer": "a" * 8001, "needs_business_data": False},
        {"answer": "test", "needs_business_data": "false"},
        {"answer": "test", "needs_business_data": False, "sources": ["fake.pdf"]},
    ],
)
def test_invalid_model_output_is_not_returned(monkeypatch, content):
    with mock_chat(
        monkeypatch, lambda _: httpx.Response(200, json=provider_response(content))
    ) as client:
        response = client.post("/api/v1/chat", json={"message": "test"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ai_invalid_response"


def test_refusal_is_a_valid_chat_outcome(monkeypatch):
    with mock_chat(
        monkeypatch, lambda _: httpx.Response(200, json=provider_response(refusal=True))
    ) as client:
        response = client.post("/api/v1/chat", json={"message": "test"})
    assert response.status_code == 200
    assert response.json()["status"] == "refused"
    assert response.json()["sources"] == response.json()["tools_used"] == []


@pytest.mark.parametrize(
    "status,code",
    [
        ("incomplete", "ai_incomplete_response"),
        ("failed", "ai_provider_error"),
    ],
)
def test_unfinished_generation_is_not_accepted(monkeypatch, status, code):
    with mock_chat(
        monkeypatch, lambda _: httpx.Response(200, json=provider_response(status=status))
    ) as client:
        response = client.post("/api/v1/chat", json={"message": "test"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == code


def test_empty_output_is_not_accepted(monkeypatch):
    payload = provider_response()
    payload["output"] = []
    with mock_chat(monkeypatch, lambda _: httpx.Response(200, json=payload)) as client:
        response = client.post("/api/v1/chat", json={"message": "test"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ai_invalid_response"


def test_unknown_usage_is_not_fabricated(monkeypatch, capsys):
    payload = provider_response()
    payload["usage"] = None
    with mock_chat(monkeypatch, lambda _: httpx.Response(200, json=payload)) as client:
        response = client.post("/api/v1/chat", json={"message": "test"})
    assert response.status_code == 200
    assert '"input_tokens": null' in capsys.readouterr().err


def test_settings_read_key_alias_without_exposing_secret(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-value")
    settings = Settings(_env_file=None)
    assert settings.openai_api_key.get_secret_value() == "test-private-value"
    assert "test-private-value" not in repr(settings)
    assert "test-private-value" not in settings.model_dump_json()
    assert ModelAnswer.model_json_schema()["additionalProperties"] is False
