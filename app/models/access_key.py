from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.core.db import Base


class AccessKey(Base):
    __tablename__ = "access_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    

    # совместимость со старой логикой
    key_value: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="free")
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # новая VPN-логика — пока делаем мягко
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=True, index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=True, index=True)
    server_id: Mapped[int | None] = mapped_column(ForeignKey("servers.id", ondelete="SET NULL"), nullable=True, index=True)

    uuid: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    external_client_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    vless_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    subscription_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user = relationship("User", back_populates="access_keys", foreign_keys=[user_id])
    subscription = relationship("Subscription", back_populates="access_keys", foreign_keys=[subscription_id])
    device = relationship("Device", back_populates="access_keys", foreign_keys=[device_id])
    server = relationship("Server", back_populates="access_keys", foreign_keys=[server_id])