from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.documents import DocumentSource


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    use_documents: bool = False
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    answer: str
    status: Literal["general_answer", "insufficient_data", "refused", "grounded_answer"]
    sources: list[DocumentSource] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    trace_id: UUID
