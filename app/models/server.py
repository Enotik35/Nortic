from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.core.db import Base


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    host: Mapped[str] = mapped_column(String(255), nullable=False)   # IP или домен
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=443)

    public_key: Mapped[str] = mapped_column(String(255), nullable=False)
    short_id: Mapped[str] = mapped_column(String(32), nullable=False)
    sni: Mapped[str] = mapped_column(String(255), nullable=False, default="www.cloudflare.com")

    flow: Mapped[str] = mapped_column(String(64), nullable=False, default="xtls-rprx-vision")
    security: Mapped[str] = mapped_column(String(32), nullable=False, default="reality")
    transport: Mapped[str] = mapped_column(String(32), nullable=False, default="tcp")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    access_keys = relationship(
    "AccessKey",
    back_populates="server",
    foreign_keys="AccessKey.server_id",
    )

    def __repr__(self) -> str:
        return f"<Server id={self.id} name={self.name!r} host={self.host}:{self.port} active={self.is_active}>"