"""Operational data. Money uses decimal, deadlines use timezone-aware timestamps."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Record


class User(Record, Base):
    __tablename__ = "users"
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    role: Mapped[str] = mapped_column(String(30), default="operator")


class Customer(Record, Base):
    __tablename__ = "customers"
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    city: Mapped[str] = mapped_column(String(80), index=True)
    address: Mapped[str] = mapped_column(String(250))
    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Supplier(Record, Base):
    __tablename__ = "suppliers"
    name: Mapped[str] = mapped_column(String(120), unique=True)
    city: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    orders: Mapped[list["Order"]] = relationship(back_populates="supplier")
    sla: Mapped["SupplierSLA"] = relationship(back_populates="supplier")


class SupplierSLA(Record, Base):
    __tablename__ = "supplier_sla"
    __table_args__ = (
        CheckConstraint("confirmation_minutes > 0", name="positive_confirmation"),
        CheckConstraint("handoff_minutes > 0", name="positive_handoff"),
    )
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), unique=True)
    confirmation_minutes: Mapped[int]
    handoff_minutes: Mapped[int]
    supplier: Mapped[Supplier] = relationship(back_populates="sla")


class Courier(Record, Base):
    __tablename__ = "couriers"
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    city: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    deliveries: Mapped[list["Delivery"]] = relationship(back_populates="courier")


class Order(Record, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="nonnegative_total"),
        CheckConstraint(
            "status IN ('confirmed', 'in_transit', 'delivered', 'cancelled')", name="status"
        ),
        CheckConstraint("promised_at >= created_at", name="deadline_after_creation"),
    )
    reference: Mapped[str] = mapped_column(String(40), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    city: Mapped[str] = mapped_column(String(80), index=True)
    delivery_address: Mapped[str] = mapped_column(String(250))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="KZT")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Snapshot the contractual limits; later SLA edits must not rewrite history.
    confirmation_sla_minutes: Mapped[int]
    handoff_sla_minutes: Mapped[int]
    customer: Mapped[Customer] = relationship(back_populates="orders")
    supplier: Mapped[Supplier] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")
    delivery: Mapped["Delivery | None"] = relationship(back_populates="order")


class OrderItem(Record, Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("unit_price >= 0", name="nonnegative_price"),
    )
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    order: Mapped[Order] = relationship(back_populates="items")


class Delivery(Record, Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint(
            "delivered_at IS NULL OR picked_up_at IS NOT NULL", name="delivery_requires_pickup"
        ),
        CheckConstraint("delivered_at >= picked_up_at", name="delivery_after_pickup"),
    )
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    courier_id: Mapped[int] = mapped_column(ForeignKey("couriers.id"), index=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delay_reason: Mapped[str | None] = mapped_column(String(40))
    order: Mapped[Order] = relationship(back_populates="delivery")
    courier: Mapped[Courier] = relationship(back_populates="deliveries")
    events: Mapped[list["DeliveryEvent"]] = relationship(
        back_populates="delivery", order_by="DeliveryEvent.occurred_at"
    )


class DeliveryEvent(Record, Base):
    __tablename__ = "delivery_events"
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    description: Mapped[str] = mapped_column(Text)
    delivery: Mapped[Delivery] = relationship(back_populates="events")


class Task(Record, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'in_progress', 'done', 'cancelled')", name="status"),
    )
    title: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="open")
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), index=True)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
