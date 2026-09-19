from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import ChatService

router = APIRouter(tags=["chat"])


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponse:
    """Single-turn basic AI. Business tools and document retrieval are not connected yet."""
    return await service.reply(body.message)
