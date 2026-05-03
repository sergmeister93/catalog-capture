"""
SQLAlchemy session factory and FastAPI dependency.

Inputs:  settings.DATABASE_URL
Outputs:
  - engine       — SQLAlchemy Engine (used by Alembic and tests)
  - SessionLocal — sessionmaker factory
  - get_db()     — FastAPI Depends generator that yields a session and
                   commits/rolls back on exit

Usage in a route handler:
    from service_photo.db.session import get_db
    from sqlalchemy.orm import Session

    def my_route(db: Session = Depends(get_db)):
        ...
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from service_photo.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,       # detect stale connections
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    class_=Session,
)


def get_db():
    """FastAPI dependency that provides a database session per request."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
