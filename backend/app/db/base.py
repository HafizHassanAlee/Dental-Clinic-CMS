from datetime import datetime, timezone
from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """SQLAlchemy 2.x DeclarativeBase for all normalized PostgreSQL entities."""
    pass
