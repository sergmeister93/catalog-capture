"""
SQLAlchemy declarative base shared by all ORM models.

All model classes in service_photo/models/ must inherit from Base.
Alembic's env.py imports Base.metadata for autogenerate support.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
