"""Thin OpenAI adapter: request a schema, inspect status, validate model output."""

import asyncio

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import ValidationError

from app.ai.contracts import ModelAnswer, ModelResult, RAGAnswer
from app.ai.prompts import RAG_INSTRUCTIONS, SYSTEM_INSTRUCTIONS
from app.core.config import Settings
from app.core.exceptions import AppError


def build_openai_client(settings: Settings) -> AsyncOpenAI | None:
    if settings.openai_api_key is None:
        return None
    return AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        base_url="https://api.openai.com/v1",
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )


def ai_error(code: str, message: str, status: int = 502) -> AppError:
    return AppError(status_code=status, code=code, message=message)


class OpenAIChatClient:
    def __init__(self, client: AsyncOpenAI | None, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    async def generate(self, message: str, *, rag: bool = False) -> ModelResult:
        if self.client is None:
            raise ai_error("ai_not_configured", "OpenAI API key is not configured", 503)
        try:
            # The total deadline includes retries and backoff, unlike a socket read timeout.
            async with asyncio.timeout(self.settings.chat_deadline_seconds):
                response = await self.client.responses.create(
                    model=self.settings.openai_model,
                    instructions=RAG_INSTRUCTIONS if rag else SYSTEM_INSTRUCTIONS,
                    input=[{"role": "user", "content": message}],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "copilot_answer",
                            "strict": True,
                            "schema": (RAGAnswer if rag else ModelAnswer).model_json_schema(),
                        }
                    },
                    max_output_tokens=self.settings.openai_max_output_tokens,
                    store=False,
                )
        except (APITimeoutError, TimeoutError):
            raise ai_error("ai_timeout", "The AI request timed out", 504) from None
        except RateLimitError:
            raise ai_error(
                "ai_rate_limited", "AI provider rate or quota limit reached", 429
            ) from None
        except (AuthenticationError, PermissionDeniedError):
            raise ai_error(
                "ai_access_error", "AI provider access is not configured correctly", 503
            ) from None
        except APIConnectionError:
            raise ai_error(
                "ai_unavailable", "AI provider is temporarily unavailable", 503
            ) from None
        except APIStatusError as exc:
            status = 503 if exc.status_code >= 500 else 502
            raise ai_error(
                "ai_provider_error", "AI provider could not process the request", status
            ) from None
        except APIError:
            raise ai_error(
                "ai_invalid_response", "AI provider returned an invalid response"
            ) from None

        if response.status == "incomplete":
            raise ai_error(
                "ai_incomplete_response", "AI response was incomplete; try a shorter request"
            )
        if response.status != "completed" or response.error is not None:
            raise ai_error("ai_provider_error", "AI provider did not complete the request")
        refused = any(
            part.type == "refusal"
            for item in response.output
            if item.type == "message"
            for part in item.content
        )
        content = None
        if not refused:
            try:
                content = (RAGAnswer if rag else ModelAnswer).model_validate_json(
                    response.output_text
                )
            except ValidationError:
                raise ai_error("ai_invalid_response", "AI response failed validation") from None
        return ModelResult(
            content=content,
            refused=refused,
            model=response.model,
            provider_response_id=response.id,
            input_tokens=response.usage.input_tokens if response.usage else None,
            output_tokens=response.usage.output_tokens if response.usage else None,
        )
