from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, field_validator


class ModelAnswer(BaseModel):
    """Only content decisions belong to the model; evidence and IDs belong to us."""

    model_config = ConfigDict(extra="forbid", strict=True)

    answer: str
    needs_business_data: bool

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 8000:
            raise ValueError("Answer must contain between 1 and 8000 characters")
        return value


@dataclass(frozen=True)
class ModelResult:
    content: ModelAnswer | RAGAnswer | None
    refused: bool
    model: str
    provider_response_id: str
    input_tokens: int | None
    output_tokens: int | None


class RAGAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    answer: str
    supported: bool
    chunk_ids: list[int]
