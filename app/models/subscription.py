from datetime import datetime
from sqlalchemy import ForeignKey, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base
from sqlalchemy import Integer
from sqlalchemy.orm import relationship, Mapped, mapped_column


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    subscription_number: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="active")
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    access_key_id: Mapped[int | None] = mapped_column(ForeignKey("access_keys.id"), nullable=True)

    device_limit_snapshot: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    devices = relationship(
    "Device",
    back_populates="subscription",
    foreign_keys="Device.subscription_id",
    cascade="all, delete-orphan",
    )   

    access_keys = relationship(
    "AccessKey",
    back_populates="subscription",
    foreign_keys="AccessKey.subscription_id",
    cascade="all, delete-orphan",
    )