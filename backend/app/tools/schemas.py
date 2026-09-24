"""Explicit input schemas and JSON-safe tool output contracts."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PositiveID = Annotated[int, Field(strict=True, gt=0, le=2147483647)]
OrderStatus = Literal["confirmed", "in_transit", "delivered", "cancelled"]


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class OrderArguments(Arguments):
    order_id: PositiveID


class CustomerArguments(Arguments):
    customer_id: PositiveID


class SupplierArguments(Arguments):
    supplier_id: PositiveID


class SearchOrdersArguments(Arguments):
    customer_id: PositiveID | None = None
    supplier_id: PositiveID | None = None
    status: OrderStatus | None = None
    city: str | None = Field(default=None, min_length=1, max_length=80)
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=10000)


class SearchCustomersArguments(Arguments):
    query: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=10000)


class SearchDocumentsArguments(Arguments):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=10)


class ToolSource(BaseModel):
    kind: Literal["database", "document"]
    table: str | None = None
    filters: dict[str, int | str] = Field(default_factory=dict)
    record_ids: list[int] = Field(default_factory=list)
    document_id: int | None = None
    chunk_id: int | None = None
    filename: str | None = None
    page_number: int | None = None


class ToolData(BaseModel):
    data: dict[str, Any]
    sources: list[ToolSource] = Field(default_factory=list)


class ToolError(BaseModel):
    code: str
    message: str


class ToolResult(BaseModel):
    tool_name: str
    status: Literal["success", "error"]
    data: dict[str, Any] | None = None
    sources: list[ToolSource] = Field(default_factory=list)
    error: ToolError | None = None
    duration_ms: float


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool = True
