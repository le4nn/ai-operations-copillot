import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.seed import DEFAULT_AS_OF, seed_data
from app.main import create_app
from app.models.business import Customer, Delivery, Order, Supplier
from app.schemas.documents import DocumentSource
from app.tools.registry import Tool, ToolRegistry, build_tool_registry
from app.tools.repository import OperationsRepository
from app.tools.schemas import OrderArguments, ToolData


@pytest.fixture
def registry(database):
    with Session(database) as session, session.begin():
        seed_data(session)
    return build_tool_registry(
        OperationsRepository(sessionmaker(database)), AsyncMock(), clock=lambda: DEFAULT_AS_OF
    )


def call(registry, name, args, allowed=None):
    return asyncio.run(
        registry.execute(name, args, allowed_tools=registry.names if allowed is None else allowed)
    )


def test_order_customer_supplier_and_delivery(registry, database):
    order = call(registry, "get_order", {"order_id": 1})
    assert order.status == "success"
    assert order.data["reference"] == "DEMO-0001"
    assert isinstance(order.data["total_amount"], str)
    assert order.data["items"]
    assert "delivery_address" not in order.data
    customer = call(registry, "get_customer", {"customer_id": order.data["customer_id"]})
    assert set(customer.data) == {"id", "name", "city"}
    supplier = call(registry, "get_supplier", {"supplier_id": order.data["supplier_id"]})
    assert supplier.data["sla"]["handoff_minutes"] == 120
    delivery = call(registry, "get_delivery_status", {"order_id": 1})
    assert delivery.data["delivery"]["events"]
    assert [s.table for s in delivery.sources] == ["orders", "deliveries", "delivery_events"]
    times = [e["occurred_at"] for e in delivery.data["delivery"]["events"]]
    assert times == sorted(times)
    with Session(database) as session:
        cancelled = session.scalar(select(Order.id).where(Order.status == "cancelled"))
    no_delivery = call(registry, "get_delivery_status", {"order_id": cancelled})
    assert no_delivery.status == "success"
    assert no_delivery.data["delivery"] is None


@pytest.mark.parametrize(
    "name,key",
    [
        ("get_order", "order_id"),
        ("get_customer", "customer_id"),
        ("get_supplier", "supplier_id"),
        ("get_delivery_status", "order_id"),
        ("get_supplier_statistics", "supplier_id"),
    ],
)
def test_missing_records_are_explicit(registry, name, key):
    result = call(registry, name, {key: 2147483647})
    assert result.status == "error"
    assert result.error.code == "resource_not_found"
    assert result.data is None
    assert result.sources == []


def test_search_is_bounded_filtered_and_not_a_count(registry):
    first = call(registry, "search_orders", {"status": "delivered", "city": "Астана", "limit": 3})
    second = call(
        registry,
        "search_orders",
        {"status": "delivered", "city": "Астана", "limit": 3, "offset": 3},
    )
    assert first.data["has_more"] is True
    assert len(first.data["items"]) == 3
    assert all(o["status"] == "delivered" and o["city"] == "Астана" for o in first.data["items"])
    assert {o["id"] for o in first.data["items"]}.isdisjoint(o["id"] for o in second.data["items"])
    assert "total" not in first.data
    assert call(registry, "search_orders", {"city": "' OR 1=1 --"}).data["items"] == []


def test_customer_search_escapes_wildcards(registry, database):
    with Session(database) as session, session.begin():
        session.add(
            Customer(
                name="Special %_ customer",
                email="special@example.test",
                city="Test",
                address="Test",
            )
        )
    response = call(registry, "search_customers", {"query": "%_"})
    assert [c["name"] for c in response.data["items"]] == ["Special %_ customer"]
    assert call(registry, "search_customers", {"query": "' OR 1=1 --"}).data["items"] == []


def test_statistics_match_seed_and_ignore_changed_supplier_sla(registry, database):
    totals = {
        key: 0
        for key in (
            "total_orders",
            "delivered_orders",
            "cancelled_orders",
            "active_orders",
            "delivered_late",
            "active_overdue",
            "handoff_sla_violations",
        )
    }
    with Session(database) as session:
        ids = list(session.scalars(select(Supplier.id)))
    for supplier_id in ids:
        result = call(registry, "get_supplier_statistics", {"supplier_id": supplier_id})
        assert result.status == "success"
        assert result.data["as_of"] == DEFAULT_AS_OF.isoformat()
        for key in totals:
            totals[key] += result.data[key]
    assert totals == {
        "total_orders": 600,
        "delivered_orders": 360,
        "cancelled_orders": 60,
        "active_orders": 180,
        "delivered_late": 180,
        "active_overdue": 120,
        "handoff_sla_violations": 120,
    }
    before = call(registry, "get_supplier_statistics", {"supplier_id": ids[0]}).data
    with Session(database) as session, session.begin():
        session.get(Supplier, ids[0]).sla.handoff_minutes = 1
    assert call(registry, "get_supplier_statistics", {"supplier_id": ids[0]}).data == before


def test_statistics_exact_deadline_and_empty_supplier(registry, database):
    with Session(database) as session, session.begin():
        order = session.get(Order, 1)
        delivery = session.scalar(select(Delivery).where(Delivery.order_id == order.id))
        supplier_id = order.supplier_id
        # Put every other order outside this supplier's aggregate to isolate the boundary.
        for other in session.scalars(
            select(Order).where(Order.supplier_id == supplier_id, Order.id != 1)
        ):
            other.supplier_id = supplier_id % 24 + 1
        delivery.picked_up_at = order.confirmed_at + timedelta(minutes=order.handoff_sla_minutes)
        delivery.delivered_at = max(delivery.picked_up_at, order.promised_at)
        order.promised_at = delivery.delivered_at
        empty = Supplier(name="Empty supplier", city="Test", active=True)
        session.add(empty)
        session.flush()
        empty_id = empty.id
    data = call(registry, "get_supplier_statistics", {"supplier_id": supplier_id}).data
    assert data["handoff_sla_violations"] == data["delivered_late"] == 0
    empty = call(registry, "get_supplier_statistics", {"supplier_id": empty_id})
    assert empty.status == "success" and empty.data["total_orders"] == 0


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"order_id": "1"},
        {"order_id": True},
        {"order_id": 0},
        {"order_id": -1},
        {"order_id": 1, "sql": "DROP TABLE orders"},
        {"order_id": 2147483648},
    ],
)
def test_invalid_arguments_never_reach_handler(arguments):
    handler = AsyncMock()
    registry = ToolRegistry([Tool("get_order", "Read order", OrderArguments, handler)])
    result = call(registry, "get_order", arguments)
    assert result.error.code == "invalid_tool_arguments"
    handler.assert_not_called()


def test_permissions_unknown_names_and_schema_discovery():
    handler = AsyncMock()
    registry = ToolRegistry([Tool("get_order", "Read order", OrderArguments, handler)])
    assert registry.definitions(frozenset()) == []
    schema = registry.definitions(registry.names)[0].input_schema
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["order_id"]
    assert call(registry, "get_order", {"order_id": 1}, frozenset()).error.code == "tool_forbidden"
    assert call(registry, "create_internal_task", {}).error.code == "unknown_tool"
    handler.assert_not_called()


@pytest.mark.parametrize(
    "exception,code",
    [
        (OperationalError("SELECT password", {}, Exception("secret")), "database_unavailable"),
        (RuntimeError("secret"), "tool_execution_failed"),
        (TimeoutError("secret"), "tool_timeout"),
    ],
)
def test_safe_error_results(exception, code):
    registry = ToolRegistry(
        [Tool("get_order", "Read order", OrderArguments, AsyncMock(side_effect=exception))]
    )
    result = call(registry, "get_order", {"order_id": 1})
    assert result.error.code == code
    assert "secret" not in result.model_dump_json()


def test_execution_timeout():
    async def slow(_):
        await asyncio.sleep(1)
        return ToolData(data={})

    registry = ToolRegistry(
        [Tool("get_order", "Read order", OrderArguments, slow)], timeout_seconds=0.01
    )
    assert call(registry, "get_order", {"order_id": 1}).error.code == "tool_timeout"


def test_document_tool_preserves_evidence():
    documents = AsyncMock()
    documents.search.return_value = [
        DocumentSource(
            document_id=5,
            chunk_id=9,
            filename="policy.pdf",
            page_number=2,
            content="Evidence",
            similarity=0.7,
        )
    ]
    registry = build_tool_registry(None, documents)
    result = call(registry, "search_documents", {"query": "refund", "top_k": 2})
    assert result.data["chunks"][0]["content"] == "Evidence"
    assert result.sources[0].chunk_id == 9
    documents.search.assert_awaited_once_with("refund", 2)
    documents.search.return_value = []
    result = call(registry, "search_documents", {"query": "missing"})
    assert result.status == "success" and result.data == {"chunks": []} and not result.sources


def test_tools_only_execute_selects(registry, database):
    statements = []

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.lstrip().upper())

    event.listen(database, "before_cursor_execute", record)
    try:
        for name, args in [
            ("get_order", {"order_id": 1}),
            ("get_customer", {"customer_id": 1}),
            ("get_supplier", {"supplier_id": 1}),
            ("get_delivery_status", {"order_id": 1}),
            ("get_supplier_statistics", {"supplier_id": 1}),
            ("search_orders", {}),
            ("search_customers", {"query": "001"}),
        ]:
            assert call(registry, name, args).status == "success"
    finally:
        event.remove(database, "before_cursor_execute", record)
    assert statements and all(statement.startswith("SELECT") for statement in statements)


def test_debug_api_contract_and_environment_restriction():
    settings = Settings(_env_file=None, OPENAI_API_KEY=None, environment="test")
    with TestClient(create_app(settings)) as client:
        assert len(client.get("/api/v1/tools").json()) == 8
        bad = client.post("/api/v1/tools/get_order/execute", json={"arguments": {"order_id": True}})
        assert bad.status_code == 200
        assert bad.json()["error"]["code"] == "invalid_tool_arguments"
        assert (
            client.post(
                "/api/v1/tools/get_order/execute",
                json={"arguments": {}, "allowed_tools": ["get_order"]},
            ).status_code
            == 422
        )
        settings.environment = "production"
        assert client.get("/api/v1/tools").status_code == 403
        assert (
            client.post(
                "/api/v1/tools/get_order/execute", json={"arguments": {"order_id": 1}}
            ).status_code
            == 403
        )


@pytest.mark.parametrize(
    "name,args",
    [
        ("search_orders", {"limit": 51}),
        ("search_orders", {"offset": -1}),
        ("search_orders", {"status": "deleted"}),
        ("search_orders", {"city": "   "}),
        ("search_customers", {"query": ""}),
        ("search_documents", {"query": "x", "top_k": 11}),
    ],
)
def test_search_limits_are_enforced_without_io(name, args):
    registry = build_tool_registry(None, AsyncMock())
    assert call(registry, name, args).error.code == "invalid_tool_arguments"
