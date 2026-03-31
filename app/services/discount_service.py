from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.friend_discounts import get_active_friend_discount_by_telegram_id
from app.repositories.referrals import count_paid_referrals


REFERRAL_DISCOUNT_RULES = [
    (10, 20),
    (5, 15),
    (3, 10),
    (1, 5),
]


def calculate_referral_discount_percent(paid_referrals_count: int) -> int:
    for min_count, discount_percent in REFERRAL_DISCOUNT_RULES:
        if paid_referrals_count >= min_count:
            return discount_percent
    return 0


async def get_friend_discount_percent(session: AsyncSession, telegram_id: int) -> int:
    discount = await get_active_friend_discount_by_telegram_id(session, telegram_id)
    if not discount:
        return 0
    return discount.discount_percent


async def get_referral_discount_percent(session: AsyncSession, user_id: int) -> int:
    paid_referrals_count = await count_paid_referrals(session, user_id)
    return calculate_referral_discount_percent(paid_referrals_count)


async def get_best_discount_percent(
    session: AsyncSession,
    *,
    user_id: int,
    telegram_id: int,
) -> int:
    friend_discount = await get_friend_discount_percent(session, telegram_id)
    referral_discount = await get_referral_discount_percent(session, user_id)
    return max(friend_discount, referral_discount)


async def get_best_discount_details(
    session: AsyncSession,
    *,
    user_id: int,
    telegram_id: int,
) -> tuple[int, str | None, int | None]:
    friend_discount = await get_active_friend_discount_by_telegram_id(session, telegram_id)
    friend_discount_percent = friend_discount.discount_percent if friend_discount else 0
    referral_discount_percent = await get_referral_discount_percent(session, user_id)

    if friend_discount_percent >= referral_discount_percent and friend_discount_percent > 0:
        return friend_discount_percent, "friend", friend_discount.id

    if referral_discount_percent > 0:
        return referral_discount_percent, "referral", None

    return 0, None, None


def apply_discount(price_rub: int, discount_percent: int) -> int:
    if price_rub <= 0:
        return 0
    if discount_percent <= 0:
        return price_rub
    discounted = round(price_rub * (100 - discount_percent) / 100)
    return max(discounted, 1)
