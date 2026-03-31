from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.subscription import Subscription
from app.models.user import User


async def get_active_subscription(session: AsyncSession, user_id: int) -> Subscription | None:
    result = await session.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .where(Subscription.status == "active")
        .order_by(Subscription.end_at.desc())
    )
    subscription = result.scalars().first()
    if subscription and subscription.end_at < datetime.utcnow():
        subscription.status = "expired"
        await session.flush()
        await session.refresh(subscription)
    return subscription if subscription and subscription.status == "active" else None
