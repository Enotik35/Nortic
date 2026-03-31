from sqlalchemy import String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base
from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column


class Tariff(Base):
    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    duration_days: Mapped[int] = mapped_column(Integer)
    price_rub: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    device_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    traffic_limit_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_trial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)