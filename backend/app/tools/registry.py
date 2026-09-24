"""Allowlisted dispatch, validation, controlled failures and safe execution events."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import AppError
from app.rag.service import DocumentService
from app.tools.repository import OperationsRepository
from app.tools.schemas import (
    CustomerArguments,
    OrderArguments,
    SearchCustomersArguments,
    SearchDocumentsArguments,
    SearchOrdersArguments,
    SupplierArguments,
    ToolData,
    ToolDefinition,
    ToolError,
    ToolResult,
    ToolSource,
)

logger = logging.getLogger("app.tools")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    arguments: type[BaseModel]
    handler: Callable[[Any], Awaitable[ToolData]]


class ToolRegistry:
    def __init__(self, tools: list[Tool], timeout_seconds: float = 100):
        self._tools = {tool.name: tool for tool in tools}
        if len(self._tools) != len(tools):
            raise ValueError("Duplicate tool name")
        self.timeout_seconds = timeout_seconds

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._tools)

    def definitions(self, allowed_tools: frozenset[str]) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                input_schema=tool.arguments.model_json_schema(),
            )
            for tool in self._tools.values()
            if tool.name in allowed_tools
        ]

    async def execute(
        self, name: str, arguments: dict[str, Any], *, allowed_tools: frozenset[str]
    ) -> ToolResult:
        """Permissions are supplied by trusted server code, never model arguments."""
        started = perf_counter()
        data = None
        sources = []
        error = None
        try:
            tool = self._tools.get(name)
            if tool is None:
                raise AppError(status_code=404, code="unknown_tool", message="Unknown tool")
            if name not in allowed_tools:
                raise AppError(
                    status_code=403, code="tool_forbidden", message="Tool is not permitted"
                )
            parsed = tool.arguments.model_validate(arguments)
            async with asyncio.timeout(self.timeout_seconds):
                output = await tool.handler(parsed)
            data, sources = output.data, output.sources
        except ValidationError:
            error = ToolError(
                code="invalid_tool_arguments", message="Arguments do not match tool schema"
            )
        except AppError as exc:
            error = ToolError(code=exc.code, message=exc.message)
        except SQLAlchemyError:
            error = ToolError(
                code="database_unavailable", message="Tool could not read the database"
            )
        except TimeoutError:
            error = ToolError(code="tool_timeout", message="Tool execution timed out")
        except Exception:  # noqa: BLE001 - tool boundary never exposes internal exception details
            error = ToolError(code="tool_execution_failed", message="Tool execution failed")
        result = ToolResult(
            tool_name=name,
            status="error" if error else "success",
            data=data,
            sources=sources,
            error=error,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        logger.info(
            "tool_execution_completed",
            extra={
                "tool_name": name if name in self._tools else "unknown",
                "status": result.status,
                "duration_ms": result.duration_ms,
                "error_code": error.code if error else None,
            },
        )
        return result


def build_tool_registry(
    repository: OperationsRepository,
    documents: DocumentService,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ToolRegistry:
    async def order(args: OrderArguments) -> ToolData:
        return await run_in_threadpool(repository.get_order, args.order_id)

    async def customer(args: CustomerArguments) -> ToolData:
        return await run_in_threadpool(repository.get_customer, args.customer_id)

    async def supplier(args: SupplierArguments) -> ToolData:
        return await run_in_threadpool(repository.get_supplier, args.supplier_id)

    async def delivery(args: OrderArguments) -> ToolData:
        return await run_in_threadpool(repository.get_delivery_status, args.order_id)

    async def orders(args: SearchOrdersArguments) -> ToolData:
        return await run_in_threadpool(repository.search_orders, args)

    async def customers(args: SearchCustomersArguments) -> ToolData:
        return await run_in_threadpool(repository.search_customers, args)

    async def statistics(args: SupplierArguments) -> ToolData:
        return await run_in_threadpool(
            repository.get_supplier_statistics, args.supplier_id, clock()
        )

    async def search_documents(args: SearchDocumentsArguments) -> ToolData:
        chunks = await documents.search(args.query, args.top_k)
        return ToolData(
            data={"chunks": [chunk.model_dump(mode="json") for chunk in chunks]},
            sources=[
                ToolSource(
                    kind="document",
                    document_id=c.document_id,
                    chunk_id=c.chunk_id,
                    filename=c.filename,
                    page_number=c.page_number,
                )
                for c in chunks
            ],
        )

    return ToolRegistry(
        [
            Tool(
                "get_order",
                "Read one order and up to 50 line items by numeric ID. No delivery address.",
                OrderArguments,
                order,
            ),
            Tool(
                "get_customer",
                "Read customer ID, name and city. Use search_orders for order history.",
                CustomerArguments,
                customer,
            ),
            Tool(
                "get_supplier",
                "Read supplier profile and current SLA. Orders retain their own SLA snapshots.",
                SupplierArguments,
                supplier,
            ),
            Tool(
                "get_delivery_status",
                "Read order status, delivery timestamps and latest 50 events. Null delivery means no delivery record.",
                OrderArguments,
                delivery,
            ),
            Tool(
                "search_orders",
                "Read a bounded order page with exact filters. This is not an aggregate count.",
                SearchOrdersArguments,
                orders,
            ),
            Tool(
                "search_customers",
                "Find customers by literal name substring; no contact details returned.",
                SearchCustomersArguments,
                customers,
            ),
            Tool(
                "get_supplier_statistics",
                "Lifetime counts for a supplier in current state; open deadlines use server time. Not a historical snapshot or today's count.",
                SupplierArguments,
                statistics,
            ),
            Tool(
                "search_documents",
                "Semantic search in uploaded policies. Empty chunks means no relevant evidence. Policies do not contain live order status.",
                SearchDocumentsArguments,
                search_documents,
            ),
        ]
    )
