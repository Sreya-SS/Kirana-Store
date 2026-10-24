"""ORM models for KiranaIQ.

Tables:
  items  -- the SKUs the store tracks
  sales  -- one row per item per day (SYNTHETIC in the demo, see seed.py)
  alerts -- stockout warnings produced by alerts.py
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    unit: Mapped[str] = mapped_column(String, nullable=False)  # kg, litre, packet, piece
    current_stock: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    reorder_level: Mapped[float] = mapped_column(Float, nullable=False, default=0)

    sales: Mapped[list["Sale"]] = relationship(back_populates="item", cascade="all, delete-orphan")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="item", cascade="all, delete-orphan")


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    qty: Mapped[float] = mapped_column(Float, nullable=False)

    item: Mapped["Item"] = relationship(back_populates="sales")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False, index=True)
    message: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # True = useful, False = not useful, None = no feedback yet.
    useful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    item: Mapped["Item"] = relationship(back_populates="alerts")
