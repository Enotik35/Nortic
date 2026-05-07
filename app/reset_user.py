import argparse
import asyncio

from sqlalchemy import delete, or_, select, update

from app.core.db import AsyncSessionLocal
from app.models.access_key import AccessKey
from app.models.device import Device
from app.models.order import Order
from app.models.receipt_task import ReceiptTask
from app.models.referral import Referral
from app.models.subscription import Subscription
from app.models.user import User


async def reset_user_by_telegram_id(telegram_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            return False

        user_id = user.id

        # Break the self-reference so deleting the user does not leave dangling refs.
        await session.execute(
            update(User)
            .where(User.referred_by_user_id == user_id)
            .values(referred_by_user_id=None)
        )

        await session.execute(
            delete(Referral).where(
                (Referral.referrer_user_id == user_id)
                | (Referral.referred_user_id == user_id)
            )
        )
        await session.execute(delete(AccessKey).where(AccessKey.user_id == user_id))
        await session.execute(delete(Device).where(Device.user_id == user_id))
        await session.execute(delete(Subscription).where(Subscription.user_id == user_id))
        await session.execute(
            delete(ReceiptTask).where(
                or_(
                    ReceiptTask.user_id == user_id,
                    ReceiptTask.order_id.in_(
                        select(Order.id).where(Order.user_id == user_id)
                    ),
                )
            )
        )
        await session.execute(delete(Order).where(Order.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))

        await session.commit()
        return True


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove a Telegram user and all bot-related data so they can start fresh."
    )
    parser.add_argument("telegram_id", type=int, help="Telegram user id to reset")
    args = parser.parse_args()

    deleted = await reset_user_by_telegram_id(args.telegram_id)
    if deleted:
        print(f"User {args.telegram_id} was reset")
    else:
        print(f"User {args.telegram_id} was not found")


if __name__ == "__main__":
    asyncio.run(main())
