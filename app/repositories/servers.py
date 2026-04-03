from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.server import Server


async def get_active_server(session: AsyncSession) -> Server | None:
    result = await session.execute(
        select(Server)
        .where(Server.is_active.is_(True))
        .order_by(Server.id.asc())
    )
    return result.scalars().first()
