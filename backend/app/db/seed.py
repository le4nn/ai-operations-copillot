"""Deterministic synthetic dataset; run explicitly with python -m app.db.seed."""

import argparse
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from random import Random

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import build_engine
from app.models import (
    Courier,
    Customer,
    Delivery,
    DeliveryEvent,
    Order,
    OrderItem,
    Supplier,
    SupplierSLA,
    User,
)

CITIES = ("Астана", "Алматы", "Шымкент", "Караганда")
DEFAULT_AS_OF = datetime(2026, 9, 18, 12, tzinfo=UTC)


def seed_data(session: Session, *, as_of: datetime = DEFAULT_AS_OF) -> bool:
    """Populate an empty database in caller-owned transaction. Never erase data."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must include a timezone")
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(31032026)"))
    references = set(session.scalars(select(Order.reference).where(Order.reference.like("DEMO-%"))))
    if references == {f"DEMO-{i:04d}" for i in range(1, 601)}:
        return False
    for table in Base.metadata.sorted_tables:
        if session.scalar(select(table.c.id).limit(1)) is not None:
            raise ValueError("Seed requires an empty database; existing data was not modified")

    rng = Random(42)
    session.add(User(name="Demo Operator", email="operator@example.test", role="operator"))
    customers = [
        Customer(
            name=f"Тестовый клиент {i + 1:03d}",
            email=f"customer{i + 1}@example.test",
            city=CITIES[i % 4],
            address=f"Учебная улица, {i + 1}",
        )
        for i in range(120)
    ]
    suppliers = [
        Supplier(
            name=f"Demo Supplier {i + 1:02d}",
            city=CITIES[i % 4],
            active=True,
            sla=SupplierSLA(confirmation_minutes=15, handoff_minutes=120),
        )
        for i in range(24)
    ]
    couriers = [
        Courier(
            name=f"Тестовый курьер {i + 1:03d}",
            email=f"courier{i + 1}@example.test",
            city=CITIES[i % 4],
            active=True,
        )
        for i in range(60)
    ]
    session.add_all([*customers, *suppliers, *couriers])
    for record in session.new:
        record.created_at = as_of - timedelta(days=60)
    session.flush()
    for i in range(600):
        city = CITIES[i % 4]
        customer = rng.choice([c for c in customers if c.city == city])
        supplier = rng.choice([s for s in suppliers if s.city == city])
        courier = rng.choice([c for c in couriers if c.city == city])
        scenario = i % 10
        # Each ten orders: 6 historical deliveries, 1 cancellation, 3 active orders.
        historical = scenario < 7
        created = as_of - (
            timedelta(days=rng.randint(1, 45), minutes=rng.randint(0, 600))
            if historical
            else timedelta(hours=6 if scenario in (7, 8) else 1)
        )
        confirmed = created + timedelta(minutes=10)
        promised = created + timedelta(hours=4)
        status = (
            "cancelled"
            if scenario == 6
            else "delivered"
            if historical
            else "in_transit"
            if scenario == 8
            else "confirmed"
        )
        items = [
            OrderItem(
                product_name=rng.choice(("Продуктовый набор", "Бытовые товары", "Канцтовары")),
                quantity=rng.randint(1, 3),
                unit_price=Decimal(rng.randint(500, 8000)),
                created_at=created,
            )
            for _ in range(rng.randint(1, 3))
        ]
        order = Order(
            reference=f"DEMO-{i + 1:04d}",
            customer=customer,
            supplier=supplier,
            status=status,
            city=city,
            delivery_address=customer.address,
            total_amount=sum((item.unit_price * item.quantity for item in items), Decimal(0)),
            currency="KZT",
            created_at=created,
            confirmed_at=confirmed,
            promised_at=promised,
            confirmation_sla_minutes=15,
            handoff_sla_minutes=120,
            items=items,
        )
        session.add(order)
        if scenario == 6:
            continue
        pickup = confirmed + timedelta(minutes=160 if scenario == 3 else 75)
        delivered = created + timedelta(hours=5 if scenario in (3, 4, 5) else 3)
        reason = {3: "supplier", 4: "courier", 5: "address", 7: "supplier", 8: "courier"}.get(
            scenario
        )
        delivery = Delivery(
            order=order,
            courier=courier,
            created_at=created,
            picked_up_at=pickup if historical or scenario == 8 else None,
            delivered_at=delivered if historical else None,
            delay_reason=reason,
        )
        session.add(delivery)
        events = [("assigned", confirmed, "Курьер назначен")]
        if delivery.picked_up_at:
            events.append(("picked_up", pickup, "Заказ передан курьеру"))
        if reason:
            events.append(("delay_reported", promised, f"Синтетическая причина задержки: {reason}"))
        if delivery.delivered_at:
            events.append(("delivered", delivered, "Заказ доставлен"))
        delivery.events = [
            DeliveryEvent(
                event_type=kind,
                occurred_at=at,
                created_at=at,
                description=description,
            )
            for kind, at, description in sorted(events, key=lambda event: event[1])
        ]
    session.flush()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of",
        type=datetime.fromisoformat,
        default=DEFAULT_AS_OF,
        help="Timezone-aware reference time; default 2026-09-18T12:00:00+00:00",
    )
    args = parser.parse_args()
    settings = get_settings()
    if settings.environment not in ("local", "test"):
        parser.error("Synthetic seed is permitted only in local/test environments")
    engine = build_engine(settings)
    try:
        with Session(engine) as session, session.begin():
            created = seed_data(session, as_of=args.as_of)
            counts = {
                model.__tablename__: session.scalar(select(func.count()).select_from(model))
                for model in (Customer, Supplier, Courier, Order, Delivery, DeliveryEvent)
            }
        print(json.dumps({"created": created, "counts": counts}, ensure_ascii=False))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
