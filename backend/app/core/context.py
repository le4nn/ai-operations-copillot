"""Request-scoped context available to log records."""

from contextvars import ContextVar

request_id_context: ContextVar[str] = ContextVar("request_id", default="system")
