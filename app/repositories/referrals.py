from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.referral import Referral


async def get_referral_by_referred_user_id(session: AsyncSession, referred_user_id: int) -> Referral | None:
    result = await session.execute(
        select(Referral).where(Referral.referred_user_id == referred_user_id)
    )
    return result.scalar_one_or_none()


async def create_referral(
    session: AsyncSession,
    *,
    referrer_user_id: int,
    referred_user_id: int,
) -> Referral:
    referral = Referral(
        referrer_user_id=referrer_user_id,
        referred_user_id=referred_user_id,
        status="registered",
    )
    session.add(referral)
    await session.flush()
    await session.refresh(referral)
    return referral


async def mark_referral_paid(session: AsyncSession, referral: Referral) -> Referral:
    referral.status = "paid"
    referral.paid_at = datetime.utcnow()
    await session.flush()
    await session.refresh(referral)
    return referral


async def count_paid_referrals(session: AsyncSession, referrer_user_id: int) -> int:
    result = await session.execute(
        select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer_user_id,
            Referral.status == "paid",
        )
    )
    return int(result.scalar() or 0)
