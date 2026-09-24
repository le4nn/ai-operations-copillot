"""ASGI application factory and production entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from app.ai.client import OpenAIChatClient, build_openai_client
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import request_context_middleware
from app.db.session import build_engine
from app.rag.embeddings import Embeddings
from app.rag.repository import DocumentRepository
from app.rag.service import DocumentService
from app.services.chat import ChatService


def create_app(settings: Settings | None = None) -> FastAPI:
    """Assemble the API from independently testable building blocks."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(settings)
        app.state.session_factory = sessionmaker(engine)
        openai_client = build_openai_client(settings)
        app.state.document_service = DocumentService(
            DocumentRepository(app.state.session_factory),
            Embeddings(openai_client),
            settings.rag_min_similarity,
        )
        app.state.chat_service = ChatService(
            OpenAIChatClient(openai_client, settings), app.state.document_service
        )
        try:
            yield
        finally:
            engine.dispose()
            if openai_client is not None:
                await openai_client.close()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.middleware("http")(request_context_middleware)
    register_exception_handlers(application)
    application.include_router(api_router)
    return application


app = create_app()
