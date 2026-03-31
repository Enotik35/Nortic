from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.core.db import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    access_keys = relationship(
    "AccessKey",
    back_populates="device",
    foreign_keys="AccessKey.device_id",
    cascade="all, delete-orphan",
    )
    user = relationship(
    "User",
    back_populates="devices",
    foreign_keys=[user_id],
    )

    subscription = relationship(
    "Subscription",
    back_populates="devices",
    foreign_keys=[subscription_id],
    )

    def __repr__(self) -> str:
        return f"<Device id={self.id} user_id={self.user_id} name={self.name!r} active={self.is_active}>"