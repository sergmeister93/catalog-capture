"""
pytest configuration and shared fixtures.

The integration tests use a real PostgreSQL database (service_photo_test).
The test database is created fresh before the session and torn down after.

Environment variable DATABASE_URL can override the default test database URL.
"""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient

# Use a separate test database to keep development data safe.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/service_photo_test",
)

# Override settings before importing the app so all components see the test DB.
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("USE_MOCK_GEMINI", "true")
os.environ.setdefault("STORAGE_BASE_PATH", "./storage_test")


@pytest.fixture(scope="session")
def test_engine():
    """Create a SQLAlchemy engine pointed at the test database."""
    from service_photo.db.base import Base
    import service_photo.models  # noqa: F401 — ensure all models are registered

    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)

    # Drop all tables and recreate from metadata for a clean slate each session.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    yield engine

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db(test_engine) -> Session:
    """
    Provide a per-test database session that is rolled back after each test.

    This keeps tests isolated without needing to recreate the schema.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = TestSession()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db) -> TestClient:
    """
    FastAPI TestClient with the test database session injected.

    Overrides the get_db dependency so all route handlers use the same
    per-test session (and therefore the same rolled-back transaction).
    """
    from service_photo.main import app
    from service_photo.db.session import get_db

    def override_get_db():
        # IMPORTANT: do NOT rollback or close the session here. The outer
        # `db` fixture owns the connection + outer transaction and rolls it
        # back at teardown. If the handler raises (e.g. HTTPException 4xx),
        # FastAPI propagates it through this generator — a rollback here
        # would wipe the shared transaction that the test itself is still
        # reading from (e.g. `db.refresh(job)` after a 400). A flush is
        # enough to push pending writes so the test can see handler state.
        yield db
        try:
            db.flush()
        except Exception:
            # Flush failures shouldn't mask the original handler outcome.
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
