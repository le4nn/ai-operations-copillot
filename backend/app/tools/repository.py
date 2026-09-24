"""Explicit SELECT queries and projections; no SQL or attribute names supplied by callers."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import ResourceNotFoundError
from app.models.business import (
    Customer,
    Delivery,
    DeliveryEvent,
    Order,
    OrderItem,
    Supplier,
    SupplierSLA,
)
from app.tools.schemas import SearchCustomersArguments, SearchOrdersArguments, ToolData, ToolSource


def project(record: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    """Only named fields leave the repository; money stays a decimal string."""
    result = {}
    for field in fields:
        value = getattr(record, field)
        if isinstance(value, datetime):
            value = utc(value).isoformat()
        elif isinstance(value, Decimal):
            value = str(value)
        result[field] = value
    return result


def utc(value: datetime) -> datetime:
    # SQLite test timestamps are naive; PostgreSQL production values are aware.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def source(table: str, *ids: int) -> ToolSource:
    return ToolSource(kind="database", table=table, record_ids=list(ids))


ORDER_FIELDS = (
    "id",
    "reference",
    "customer_id",
    "supplier_id",
    "status",
    "city",
    "total_amount",
    "currency",
    "created_at",
    "confirmed_at",
    "promised_at",
    "confirmation_sla_minutes",
    "handoff_sla_minutes",
)
CUSTOMER_FIELDS = ("id", "name", "city")


class OperationsRepository:
    def __init__(self, factory: sessionmaker[Session]):
        self.factory = factory

    @staticmethod
    def require(session: Session, model, record_id: int):
        record = session.get(model, record_id)
        if record is None:
            raise ResourceNotFoundError(model.__tablename__, record_id)
        return record

    def get_order(self, order_id: int) -> ToolData:
        with self.factory() as session:
            order = self.require(session, Order, order_id)
            items = list(
                session.scalars(
                    select(OrderItem)
                    .where(OrderItem.order_id == order_id)
                    .order_by(OrderItem.id)
                    .limit(51)
                )
            )
            data = project(order, ORDER_FIELDS)
            data["items"] = [
                project(item, ("id", "product_name", "quantity", "unit_price"))
                for item in items[:50]
            ]
            data["items_has_more"] = len(items) > 50
            return ToolData(
                data=data,
                sources=[
                    source("orders", order_id),
                    source("order_items", *(item.id for item in items[:50])),
                ],
            )

    def get_customer(self, customer_id: int) -> ToolData:
        with self.factory() as session:
            customer = self.require(session, Customer, customer_id)
            # Orders are obtained through the bounded search_orders tool.
            return ToolData(
                data=project(customer, CUSTOMER_FIELDS), sources=[source("customers", customer_id)]
            )

    def get_supplier(self, supplier_id: int) -> ToolData:
        with self.factory() as session:
            supplier = self.require(session, Supplier, supplier_id)
            sla = session.scalar(select(SupplierSLA).where(SupplierSLA.supplier_id == supplier_id))
            data = project(supplier, ("id", "name", "city", "active"))
            data["sla"] = project(sla, ("confirmation_minutes", "handoff_minutes")) if sla else None
            sources = [source("suppliers", supplier_id)]
            if sla:
                sources.append(source("supplier_sla", sla.id))
            return ToolData(data=data, sources=sources)

    def get_delivery_status(self, order_id: int) -> ToolData:
        with self.factory() as session:
            order = self.require(session, Order, order_id)
            delivery = session.scalar(select(Delivery).where(Delivery.order_id == order_id))
            sources = [source("orders", order_id)]
            data = {"order_id": order_id, "order_status": order.status, "delivery": None}
            if delivery:
                events = list(
                    session.scalars(
                        select(DeliveryEvent)
                        .where(DeliveryEvent.delivery_id == delivery.id)
                        .order_by(DeliveryEvent.occurred_at.desc(), DeliveryEvent.id.desc())
                        .limit(51)
                    )
                )
                details = project(
                    delivery, ("id", "courier_id", "picked_up_at", "delivered_at", "delay_reason")
                )
                details["events"] = [
                    project(e, ("id", "event_type", "occurred_at", "description"))
                    for e in reversed(events[:50])
                ]
                details["events_has_more"] = len(events) > 50
                data["delivery"] = details
                sources.extend(
                    [
                        source("deliveries", delivery.id),
                        source("delivery_events", *(e.id for e in events[:50])),
                    ]
                )
            return ToolData(data=data, sources=sources)

    def search_orders(self, args: SearchOrdersArguments) -> ToolData:
        statement = select(Order)
        for field in ("customer_id", "supplier_id", "status", "city"):
            value = getattr(args, field)
            if value is not None:
                statement = statement.where(getattr(Order, field) == value)
        with self.factory() as session:
            records = list(
                session.scalars(
                    statement.order_by(Order.id).offset(args.offset).limit(args.limit + 1)
                )
            )
            page = records[: args.limit]
            return ToolData(
                data={
                    "items": [project(o, ORDER_FIELDS) for o in page],
                    "offset": args.offset,
                    "limit": args.limit,
                    "has_more": len(records) > args.limit,
                },
                sources=[source("orders", *(o.id for o in page))],
            )

    def search_customers(self, args: SearchCustomersArguments) -> ToolData:
        # autoescape ensures '%' and '_' in user input are literal characters.
        statement = select(Customer).where(Customer.name.icontains(args.query, autoescape=True))
        with self.factory() as session:
            records = list(
                session.scalars(
                    statement.order_by(Customer.id).offset(args.offset).limit(args.limit + 1)
                )
            )
            page = records[: args.limit]
            return ToolData(
                data={
                    "items": [project(c, CUSTOMER_FIELDS) for c in page],
                    "offset": args.offset,
                    "limit": args.limit,
                    "has_more": len(records) > args.limit,
                },
                sources=[source("customers", *(c.id for c in page))],
            )

    def get_supplier_statistics(self, supplier_id: int, now: datetime) -> ToolData:
        """Lifetime totals; open deadlines evaluated at the server-supplied UTC instant."""
        from sqlalchemy import and_, case, extract, literal

        with self.factory() as session:
            self.require(session, Supplier, supplier_id)
            end = func.coalesce(Delivery.picked_up_at, literal(now))
            if session.get_bind().dialect.name == "sqlite":
                elapsed = func.round(
                    (func.julianday(end) - func.julianday(Order.confirmed_at)) * 86400, 3
                )
            else:
                elapsed = extract("epoch", end) - extract("epoch", Order.confirmed_at)
            conditions = {
                "delivered_orders": Order.status == "delivered",
                "cancelled_orders": Order.status == "cancelled",
                "active_orders": Order.status.in_(("confirmed", "in_transit")),
                "delivered_late": and_(
                    Order.status == "delivered", Delivery.delivered_at > Order.promised_at
                ),
                "active_overdue": and_(
                    Order.status.in_(("confirmed", "in_transit")), Order.promised_at < now
                ),
                "handoff_sla_violations": and_(
                    Order.status != "cancelled",
                    Order.confirmed_at.is_not(None),
                    elapsed > Order.handoff_sla_minutes * 60,
                ),
                "delivered_without_timestamp": and_(
                    Order.status == "delivered", Delivery.delivered_at.is_(None)
                ),
            }
            statement = (
                select(
                    func.count(Order.id).label("total_orders"),
                    *[
                        func.coalesce(func.sum(case((condition, 1), else_=0)), 0).label(name)
                        for name, condition in conditions.items()
                    ],
                )
                .select_from(Order)
                .outerjoin(Delivery)
                .where(Order.supplier_id == supplier_id)
            )
            counts = dict(session.execute(statement).mappings().one())
            return ToolData(
                data={
                    "supplier_id": supplier_id,
                    "as_of": utc(now).isoformat(),
                    "scope": "all_orders_current_state",
                    **counts,
                },
                sources=[
                    source("suppliers", supplier_id),
                    ToolSource(
                        kind="database", table="orders", filters={"supplier_id": supplier_id}
                    ),
                    ToolSource(
                        kind="database",
                        table="deliveries",
                        filters={"orders.supplier_id": supplier_id},
                    ),
                ],
            )
