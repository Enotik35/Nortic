from app.core.config import settings
from app.models.user import User


def has_user_accepted_legal(user: User | None) -> bool:
    return bool(
        user
        and user.legal_accepted_at is not None
        and user.legal_version == settings.legal_version
    )
