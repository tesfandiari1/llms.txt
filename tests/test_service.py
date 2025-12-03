"""Unit tests for JobService - critical paths only."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("FIRECRAWL_API_KEY", "test-key")

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.base import Base
from app.jobs.models import Job, Page
from app.jobs.schemas import JobStatus
from app.jobs.service import JobService


@pytest.fixture
def db():
    """Create fresh in-memory database for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_local()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def mock_firecrawl():
    """Create mock Firecrawl client."""
    client = MagicMock()
    client.map_site.return_value = [
        "https://example.com/docs/page1",
        "https://example.com/api/page2",
    ]
    client.batch_scrape.return_value = [
        {
            "markdown": "# Page 1 content",
            "metadata": {"title": "Page 1", "sourceURL": "https://example.com/docs/page1"},
        },
        {
            "markdown": "# Page 2 content",
            "metadata": {"title": "Page 2", "sourceURL": "https://example.com/api/page2"},
        },
    ]
    return client


@pytest.fixture
def mock_summarizer():
    """Create mock Summarizer."""
    summarizer = MagicMock()
    summarizer.categorize_urls.return_value = {
        "categories": ["docs", "api"],
        "pages": [
            {"url": "https://example.com/docs/page1", "category": "docs", "importance": 80},
            {"url": "https://example.com/api/page2", "category": "api", "importance": 70},
        ],
    }
    summarizer.summarize_batch.return_value = [
        {"id": "page1", "title": "Page 1", "markdown": "content", "summary": "Summary 1"},
        {"id": "page2", "title": "Page 2", "markdown": "content", "summary": "Summary 2"},
    ]
    summarizer.generate_site_summary.return_value = {
        "title": "Example Site",
        "summary": "An example documentation site.",
        "notes": [],
    }
    return summarizer


@pytest.fixture
def mock_storage():
    """Create mock Storage."""
    storage = MagicMock()
    storage.save.return_value = "test-key/llms.txt"
    return storage


def test_process_job_full_pipeline(db, mock_firecrawl, mock_summarizer, mock_storage):
    """Full pipeline: discover -> categorize -> extract -> summarize -> generate."""
    job = Job(url="https://example.com", auto_generate=True)
    db.add(job)
    db.commit()
    db.refresh(job)

    def capture_pages(*args, **kwargs):
        pages = db.query(Page).filter(Page.job_id == job.id).all()
        return [
            {"id": str(p.id), "title": p.title or "", "markdown": p.markdown or "", "summary": f"Summary for {p.url}"}
            for p in pages
        ]

    mock_summarizer.summarize_batch.side_effect = capture_pages

    service = JobService(db, mock_firecrawl, mock_summarizer, mock_storage)
    service.process_job(job.id)

    db.refresh(job)

    assert job.status == JobStatus.COMPLETED
    assert job.progress_percent == 100  # noqa: PLR2004
    assert job.result_files is not None
    assert "llms_txt" in job.result_files
    assert "llms_ctx" in job.result_files
    assert job.site_title == "Example Site"

    mock_firecrawl.map_site.assert_called_once()
    mock_firecrawl.batch_scrape.assert_called_once()
    mock_summarizer.summarize_batch.assert_called_once()
    mock_summarizer.generate_site_summary.assert_called_once()
    assert mock_storage.save.call_count == 2  # noqa: PLR2004


def test_process_job_handles_failure(db, mock_firecrawl, mock_summarizer, mock_storage):
    """Pipeline marks job as failed on exception and re-raises for pgqueuer."""
    job = Job(url="https://example.com")
    db.add(job)
    db.commit()
    db.refresh(job)

    mock_firecrawl.map_site.side_effect = Exception("API error")

    service = JobService(db, mock_firecrawl, mock_summarizer, mock_storage)

    with pytest.raises(Exception, match="API error"):
        service.process_job(job.id)

    db.refresh(job)

    assert job.status == JobStatus.FAILED
    assert "API error" in job.error_message


def test_continue_generation_success(db, mock_firecrawl, mock_summarizer, mock_storage):
    """continue_generation runs summarization and generation for scan-only jobs."""
    job = Job(
        url="https://example.com",
        status=JobStatus.SUMMARIZING,
        auto_generate=False,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    page1 = Page(
        job_id=job.id,
        url="https://example.com/page1",
        title="Page 1",
        markdown="content",
        category="docs",
        importance_score=80,
    )
    page2 = Page(
        job_id=job.id,
        url="https://example.com/page2",
        title="Page 2",
        markdown="content",
        category="api",
        importance_score=70,
    )
    db.add_all([page1, page2])
    db.commit()

    # Mock batch_scrape to return matching results for these specific URLs
    mock_firecrawl.batch_scrape.return_value = [
        {
            "markdown": "# Page 1 content",
            "metadata": {"title": "Page 1", "sourceURL": "https://example.com/page1"},
        },
        {
            "markdown": "# Page 2 content",
            "metadata": {"title": "Page 2", "sourceURL": "https://example.com/page2"},
        },
    ]

    mock_summarizer.summarize_batch.return_value = [
        {"id": str(page1.id), "summary": "Summary 1"},
        {"id": str(page2.id), "summary": "Summary 2"},
    ]

    service = JobService(db, mock_firecrawl, mock_summarizer, mock_storage)
    service.continue_generation(job.id)

    db.refresh(job)

    assert job.status == JobStatus.COMPLETED
    assert job.result_files is not None
    mock_summarizer.summarize_batch.assert_called_once()
    assert mock_storage.save.call_count == 3  # noqa: PLR2004
