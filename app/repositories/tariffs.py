from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.tariff import Tariff


async def get_active_tariffs(session: AsyncSession) -> list[Tariff]:
    result = await session.execute(
        select(Tariff)
        .where(
            Tariff.is_active.is_(True),
            Tariff.is_trial.is_(False),
        )
        .order_by(Tariff.price_rub.asc())
    )
    return list(result.scalars().all())


async def get_tariff_by_id(session: AsyncSession, tariff_id: int) -> Tariff | None:
    result = await session.execute(select(Tariff).where(Tariff.id == tariff_id))
    return result.scalar_one_or_none()

async def get_active_trial_tariff(session: AsyncSession) -> Tariff | None:
    result = await session.execute(
        select(Tariff).where(
            Tariff.is_active.is_(True),
            Tariff.is_trial.is_(True),
        )
    )
    return result.scalar_one_or_none()
