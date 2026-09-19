import logging
from time import perf_counter
from uuid import uuid4

from app.ai.client import OpenAIChatClient
from app.core.exceptions import AppError
from app.schemas.chat import ChatResponse

logger = logging.getLogger("app.ai")
NO_DATA_ANSWER = (
    "Я не нашёл подтверждённой информации в доступных источниках. "
    "На этом этапе доступ к бизнес-данным и документам ещё не подключён."
)


class ChatService:
    def __init__(self, client: OpenAIChatClient) -> None:
        self.client = client

    async def reply(self, message: str) -> ChatResponse:
        trace_id = uuid4()
        started_at = perf_counter()
        try:
            result = await self.client.generate(message)
        except AppError as exc:
            logger.warning(
                "ai_request_failed",
                extra={
                    "trace_id": str(trace_id),
                    "error_code": exc.code,
                    "latency_ms": round((perf_counter() - started_at) * 1000, 2),
                },
            )
            raise

        if result.refused:
            response = ChatResponse(
                answer="Модель отказалась отвечать на этот запрос. Попробуйте переформулировать его.",
                status="refused",
                trace_id=trace_id,
            )
        elif result.content is None:
            raise AppError(
                status_code=502, code="ai_invalid_response", message="AI response is empty"
            )
        elif result.content.needs_business_data:
            # Discard unsupported business claims, even if the model supplied an answer.
            response = ChatResponse(
                answer=NO_DATA_ANSWER, status="insufficient_data", trace_id=trace_id
            )
        else:
            response = ChatResponse(
                answer=result.content.answer, status="general_answer", trace_id=trace_id
            )

        logger.info(
            "ai_request_completed",
            extra={
                "trace_id": str(trace_id),
                "provider_response_id": result.provider_response_id,
                "model": result.model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "outcome": response.status,
                "latency_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        return response
