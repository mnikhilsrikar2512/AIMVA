from sqlalchemy import select

from app.models import Integration, User
from app.security import encrypt_json


def connect(db, email: str, provider: str, secret: dict, meta: dict = None) -> Integration:
    """Insert a connected integration directly (simulates a finished OAuth flow)."""
    user = db.scalar(select(User).where(User.email == email))
    integ = Integration(user_id=user.id, provider=provider, account_name=provider,
                        secret=encrypt_json(secret), meta=meta or {})
    db.add(integ)
    db.commit()
    return integ
