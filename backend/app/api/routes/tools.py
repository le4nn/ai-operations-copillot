"""Local development tool inspection and execution; not a public authorization API."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from app.core.exceptions import AppError
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolDefinition, ToolResult

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    arguments: dict[str, Any]


def get_tools(request: Request) -> ToolRegistry:
    if request.app.state.settings.environment not in ("local", "test"):
        raise AppError(
            status_code=403,
            code="tool_debug_disabled",
            message="Direct tool execution is available only in local/test environments",
        )
    return request.app.state.tool_registry


@router.get("", response_model=list[ToolDefinition])
def list_tools(registry: Annotated[ToolRegistry, Depends(get_tools)]) -> list[ToolDefinition]:
    return registry.definitions(registry.names)


@router.post("/{name}/execute", response_model=ToolResult)
async def execute_tool(
    name: str, body: ToolCallRequest, registry: Annotated[ToolRegistry, Depends(get_tools)]
) -> ToolResult:
    """Execution errors are typed tool results; inspect status even when HTTP is 200."""
    return await registry.execute(name, body.arguments, allowed_tools=registry.names)
