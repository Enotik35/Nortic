import secrets
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_ref_code(session: AsyncSession, ref_code: str) -> User | None:
    result = await session.execute(select(User).where(User.ref_code == ref_code))
    return result.scalar_one_or_none()


async def get_user_by_telegram_username(session: AsyncSession, telegram_username: str) -> User | None:
    normalized = telegram_username.strip().lstrip("@").lower()
    if not normalized:
        return None

    result = await session.execute(
        select(User).where(func.lower(User.telegram_username) == normalized)
    )
    return result.scalar_one_or_none()


def generate_ref_code(telegram_id: int) -> str:
    return f"ref{telegram_id}_{secrets.token_hex(4)}"


async def ensure_user_ref_code(session: AsyncSession, user: User) -> User:
    if user.ref_code:
        return user

    user.ref_code = generate_ref_code(user.telegram_id)
    await session.flush()
    await session.refresh(user)
    return user


async def create_user_if_not_exists(
    session: AsyncSession,
    telegram_id: int,
    telegram_username: str | None,
) -> User:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user:
        return user

    user = User(
        telegram_id=telegram_id,
        telegram_username=telegram_username,
        ref_code=generate_ref_code(telegram_id),
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def update_user_email(session: AsyncSession, user: User, email: str) -> User:
    user.email = email
    await session.flush()
    await session.refresh(user)
    return user


async def set_referred_by_user(session: AsyncSession, user: User, referrer_user_id: int) -> User:
    if user.referred_by_user_id is None:
        user.referred_by_user_id = referrer_user_id
        await session.flush()
        await session.refresh(user)
    return user

async def mark_trial_used(session: AsyncSession, user: User) -> User:
    user.trial_used = True
    await session.flush()
    await session.refresh(user)
    return user


async def mark_legal_accepted(session: AsyncSession, user: User, legal_version: str) -> User:
    user.legal_accepted_at = datetime.utcnow()
    user.legal_version = legal_version
    await session.flush()
    await session.refresh(user)
    return user

