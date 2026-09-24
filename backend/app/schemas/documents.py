from pydantic import BaseModel, ConfigDict, Field


class DocumentInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    status: str


class DocumentSource(BaseModel):
    document_id: int
    chunk_id: int
    filename: str
    page_number: int | None
    content: str
    similarity: float


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=10)
