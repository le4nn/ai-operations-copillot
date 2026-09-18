"""Cross-cutting HTTP request behavior."""

import logging
import re
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.core.context import request_id_context

logger = logging.getLogger("app.http")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Attach a safe correlation ID and emit one completion log per request."""
    supplied_id = request.headers.get("X-Request-ID", "")
    request_id = supplied_id if _SAFE_REQUEST_ID.fullmatch(supplied_id) else str(uuid4())
    token = request_id_context.set(request_id)
    started_at = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled_exception")
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "An unexpected error occurred",
                        "request_id": request_id,
                    }
                },
            )
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        return response
    finally:
        request_id_context.reset(token)
