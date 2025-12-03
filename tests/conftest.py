"""Test fixtures for API tests."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("FIRECRAWL_API_KEY", "test-key")

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.base import Base
from app.database import get_db
from app.jobs import models
from app.main import app


@pytest.fixture(scope="module", autouse=True)
def patch_jsonb():
    """Replace JSONB with JSON for SQLite compatibility."""
    original_discovered_urls = models.Job.__table__.c.discovered_urls.type
    original_result_files = models.Job.__table__.c.result_files.type

    models.Job.__table__.c.discovered_urls.type = JSON()
    models.Job.__table__.c.result_files.type = JSON()

    yield

    models.Job.__table__.c.discovered_urls.type = original_discovered_urls
    models.Job.__table__.c.result_files.type = original_result_files


TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db() -> Generator[Session]:
    """Override database dependency for tests."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def db() -> Generator[Session]:
    """Create fresh database tables for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db: Session) -> Generator[TestClient]:
    """Create test client with database override."""
    app.dependency_overrides[get_db] = override_get_db

    with patch("app.main.enqueue_job"), TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def mock_storage():
    """Create mock Storage for download tests."""
    storage = MagicMock()
    storage.read.return_value = "test content"
    storage.save.return_value = "test-key"

    with patch("app.main.get_storage", return_value=storage):
        yield storage
