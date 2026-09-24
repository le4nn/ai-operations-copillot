"""One fixed embedding space for both documents and queries."""

import asyncio
import logging
import math

from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError

from app.ai.client import ai_error

MODEL = "text-embedding-3-small"
DIMENSIONS = 1536


class Embeddings:
    def __init__(self, client: AsyncOpenAI | None):
        self.client = client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.client is None:
            raise ai_error("ai_not_configured", "OpenAI API key is not configured", 503)
        if any(not text.strip() or len(text.encode("utf-8")) > 8000 for text in texts):
            raise ai_error(
                "invalid_embedding_input", "Text exceeds safe embedding input limit", 422
            )
        vectors = []
        try:
            async with asyncio.timeout(90):
                for offset in range(0, len(texts), 32):
                    batch = texts[offset : offset + 32]
                    response = await self.client.embeddings.create(
                        model=MODEL, input=batch, dimensions=DIMENSIONS, encoding_format="float"
                    )
                    logging.getLogger("app.ai").info(
                        "embeddings_completed",
                        extra={
                            "model": MODEL,
                            "input_tokens": response.usage.prompt_tokens,
                            "batch_size": len(batch),
                        },
                    )
                    items = sorted(response.data, key=lambda item: item.index)
                    if [item.index for item in items] != list(range(len(batch))):
                        raise ai_error("ai_invalid_response", "Invalid embedding batch")
                    for item in items:
                        vector = item.embedding
                        if (
                            len(vector) != DIMENSIONS
                            or not all(math.isfinite(x) for x in vector)
                            or not any(vector)
                        ):
                            raise ai_error("ai_invalid_response", "Invalid embedding vector")
                        vectors.append(vector)
        except (TimeoutError, APITimeoutError):
            raise ai_error("ai_timeout", "Embedding request timed out", 504) from None
        except RateLimitError:
            raise ai_error(
                "ai_rate_limited", "Embedding provider rate limit reached", 429
            ) from None
        except APIError:
            raise ai_error("ai_unavailable", "Embedding provider unavailable", 503) from None
        return vectors
