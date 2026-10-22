from typing import Generator
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings


def _build_engine():
    db_url = settings.sqlalchemy_database_url
    try:
        connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {"connect_timeout": 8}
        eng = create_engine(
            db_url,
            pool_pre_ping=True,
            future=True,
            connect_args=connect_args,
        )
        if os.environ.get("VERCEL") and not db_url.startswith("sqlite"):
            # Verify remote connection quickly; fall back to /tmp SQLite if DATABASE_URL is unreachable
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
        return eng
    except Exception:
        return create_engine(
            "sqlite:////tmp/rumi_dental.db",
            connect_args={"check_same_thread": False},
            future=True,
        )


engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
