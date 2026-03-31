from datetime import datetime
from sqlalchemy import BigInteger, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    trial_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
        
    ref_code: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    referred_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    referrer = relationship("User", remote_side="User.id", foreign_keys=[referred_by_user_id])

    devices = relationship(
        "Device",
        back_populates="user",
        foreign_keys="Device.user_id",
        cascade="all, delete-orphan",
    )
    
    access_keys = relationship(
        "AccessKey",
        back_populates="user",
        foreign_keys="AccessKey.user_id",
        cascade="all, delete-orphan",
    )

    sent_referrals = relationship(
        "Referral",
        foreign_keys="Referral.referrer_user_id",
        back_populates="referrer",
    )

    received_referral = relationship(
        "Referral",
        foreign_keys="Referral.referred_user_id",
        back_populates="referred",
    )