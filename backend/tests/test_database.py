from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from conftest import migration_config
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.db.base import Base
from app.db.seed import DEFAULT_AS_OF, seed_data
from app.models import Customer, Delivery, DeliveryEvent, Order, OrderItem, Supplier


def as_utc(value: datetime) -> datetime:
    # SQLite strips tzinfo; PostgreSQL can return the server's session timezone.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def test_migration_matches_models_and_round_trips(database):
    with database.begin() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []
        assert len(Base.metadata.tables) == 15
        command.downgrade(migration_config(connection), "base")
        assert set(inspect(connection).get_table_names()) == {"alembic_version"}
        command.upgrade(migration_config(connection), "head")
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_seed_counts_relationships_and_idempotence(database):
    with Session(database) as session, session.begin():
        assert seed_data(session)
    with Session(database) as session, session.begin():
        assert not seed_data(session)
        counts = {
            name: session.scalar(select(func.count()).select_from(table))
            for name, table in Base.metadata.tables.items()
        }
        assert counts["customers"] == 120
        assert counts["suppliers"] == counts["supplier_sla"] == 24
        assert counts["couriers"] == 60
        assert counts["orders"] == 600
        assert counts["deliveries"] == 540
        assert counts["delivery_events"] == 1620
        assert counts["orders"] <= counts["order_items"] <= 1800
        assert counts["ai_traces"] == counts["documents"] == 0
        for order in session.scalars(select(Order)):
            assert order.total_amount == sum(
                (item.unit_price * item.quantity for item in order.items), Decimal(0)
            )
            assert order.city == order.customer.city == order.supplier.city
            if order.delivery:
                assert order.delivery.courier.city == order.city
                times = [event.occurred_at for event in order.delivery.events]
                assert times == sorted(times)
                assert all(as_utc(at) <= DEFAULT_AS_OF for at in times)
            assert (order.delivery is None) == (order.status == "cancelled")
        delivered_late = session.scalar(
            select(func.count())
            .select_from(Order)
            .join(Delivery)
            .where(Delivery.delivered_at > Order.promised_at)
        )
        overdue = session.scalar(
            select(func.count())
            .select_from(Order)
            .where(
                Order.status.in_(("confirmed", "in_transit")),
                Order.promised_at < DEFAULT_AS_OF,
            )
        )
        assert delivered_late == 180
        assert overdue == 120
        supplier_violations = 0
        for order in session.scalars(select(Order).join(Delivery)):
            end = order.delivery.picked_up_at or DEFAULT_AS_OF
            if (
                as_utc(end) - as_utc(order.confirmed_at)
            ).total_seconds() > order.handoff_sla_minutes * 60:
                supplier_violations += 1
        assert supplier_violations == 120


def test_seed_refuses_existing_business_data_without_changes(database):
    with Session(database) as session, session.begin():
        session.add(
            Customer(name="Existing", email="existing@example.test", city="Астана", address="Test")
        )
    with (
        Session(database) as session,
        pytest.raises(ValueError, match="empty database"),
        session.begin(),
    ):
        seed_data(session)
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Customer)) == 1
        assert session.scalar(select(func.count()).select_from(Supplier)) == 0


def test_seed_transaction_rolls_back(database):
    with Session(database) as session, pytest.raises(RuntimeError), session.begin():
        seed_data(session)
        raise RuntimeError("simulated failure")
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 0
        assert session.scalar(select(func.count()).select_from(Customer)) == 0


def test_foreign_key_is_enforced(database):
    with Session(database) as session, pytest.raises(IntegrityError), session.begin():
        session.add(
            DeliveryEvent(
                delivery_id=999,
                event_type="assigned",
                occurred_at=DEFAULT_AS_OF,
                description="Missing parent",
            )
        )


@pytest.mark.parametrize("field,value", [("quantity", 0), ("unit_price", Decimal(-1))])
def test_invalid_item_is_rejected(database, field, value):
    with Session(database) as session, session.begin():
        seed_data(session)
    with Session(database) as session, pytest.raises(IntegrityError), session.begin():
        item = session.scalar(select(OrderItem).limit(1))
        setattr(item, field, value)


def test_duplicate_customer_email_is_rejected(database):
    with Session(database) as session, pytest.raises(IntegrityError), session.begin():
        session.add_all(
            [
                Customer(name="Test", email="same@example.test", city="Астана", address="Test")
                for _ in range(2)
            ]
        )


def test_seed_requires_timezone(database):
    with Session(database) as session, pytest.raises(ValueError, match="timezone"):
        seed_data(session, as_of=datetime(2026, 9, 18, tzinfo=None))  # noqa: DTZ001
