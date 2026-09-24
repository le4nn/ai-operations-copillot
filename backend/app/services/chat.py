import json
import logging
from time import perf_counter
from uuid import UUID, uuid4

from app.ai.client import OpenAIChatClient
from app.ai.contracts import RAGAnswer
from app.core.exceptions import AppError
from app.rag.service import DocumentService
from app.schemas.chat import ChatResponse

logger = logging.getLogger("app.ai")
NO_DATA_ANSWER = (
    "Я не нашёл подтверждённой информации в доступных источниках. "
    "Попробуйте уточнить вопрос или загрузить подходящий документ."
)


class ChatService:
    def __init__(self, client: OpenAIChatClient, documents: DocumentService | None = None) -> None:
        self.client = client
        self.documents = documents

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

    async def reply_with_documents(self, message: str) -> ChatResponse:
        trace_id = uuid4()
        started_at = perf_counter()
        try:
            response = await self._rag_reply(message, trace_id)
        except AppError as exc:
            logger.warning(
                "rag_request_failed", extra={"trace_id": str(trace_id), "error_code": exc.code}
            )
            raise
        logger.info(
            "rag_request_completed",
            extra={
                "trace_id": str(trace_id),
                "outcome": response.status,
                "chunk_ids": [s.chunk_id for s in response.sources],
                "latency_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        return response

    async def _rag_reply(self, message: str, trace_id: UUID) -> ChatResponse:
        if self.documents is None:
            raise AppError(status_code=503, code="rag_unavailable", message="RAG is not configured")
        sources = await self.documents.search(message)
        if not sources:
            return ChatResponse(
                answer=NO_DATA_ANSWER, status="insufficient_data", trace_id=trace_id
            )
        payload = json.dumps(
            {"question": message, "fragments": [s.model_dump() for s in sources]},
            ensure_ascii=False,
        )
        result = await self.client.generate(payload, rag=True)
        if result.refused:
            return ChatResponse(
                answer="Модель отказалась отвечать на запрос.", status="refused", trace_id=trace_id
            )
        logger.info(
            "rag_generation_completed",
            extra={
                "trace_id": str(trace_id),
                "model": result.model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            },
        )
        content = result.content
        if not isinstance(content, RAGAnswer):
            raise AppError(
                status_code=502, code="ai_invalid_response", message="Invalid RAG answer"
            )
        allowed = {source.chunk_id: source for source in sources}
        if any(chunk_id not in allowed for chunk_id in content.chunk_ids):
            raise AppError(
                status_code=502, code="ai_invalid_sources", message="Unknown source citation"
            )
        if not content.supported or not content.chunk_ids:
            return ChatResponse(
                answer=NO_DATA_ANSWER, status="insufficient_data", trace_id=trace_id
            )
        if not content.answer.strip() or len(content.answer) > 8000:
            raise AppError(
                status_code=502, code="ai_invalid_response", message="Invalid answer length"
            )
        return ChatResponse(
            answer=content.answer,
            status="grounded_answer",
            trace_id=trace_id,
            sources=[allowed[i] for i in dict.fromkeys(content.chunk_ids)],
        )
