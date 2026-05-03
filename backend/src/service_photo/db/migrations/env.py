"""
Alembic environment.

Reads DATABASE_URL from the app settings so migrations always target the
same database as the running application.

Import all ORM models before calling Base.metadata so Alembic autogenerate
can see every table.
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Import the shared declarative base.
from service_photo.db.base import Base

# Import every model module so Base.metadata is populated for autogenerate.
import service_photo.models.listing_job           # noqa: F401
import service_photo.models.listing_job_image     # noqa: F401
import service_photo.models.listing_job_status_history  # noqa: F401
import service_photo.models.listing_draft_overview      # noqa: F401
import service_photo.models.listing_draft_description   # noqa: F401
import service_photo.models.listing_draft_specifications # noqa: F401
import service_photo.models.listing_draft_accessories   # noqa: F401
import service_photo.models.listing_review_overview     # noqa: F401
import service_photo.models.listing_review_description  # noqa: F401
import service_photo.models.listing_review_specifications # noqa: F401
import service_photo.models.listing_review_accessories  # noqa: F401
import service_photo.models.listing_exports            # noqa: F401

# Pull the target metadata from the base.
target_metadata = Base.metadata

# Alembic Config object.
config = context.config

# Allow DATABASE_URL env var to override alembic.ini value.
db_url = os.environ.get("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# Set up loggers from alembic.ini if available.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script output only)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
