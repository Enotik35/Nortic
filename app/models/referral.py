from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Referral(Base):
    __tablename__ = "referrals"

    __table_args__ = (
        UniqueConstraint("referred_user_id", name="uq_referrals_referred_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    referrer_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    referred_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="registered")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    referrer = relationship(
        "User",
        foreign_keys=[referrer_user_id],
        back_populates="sent_referrals",
    )
    referred = relationship(
        "User",
        foreign_keys=[referred_user_id],
        back_populates="received_referral",
    )