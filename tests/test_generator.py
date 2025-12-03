"""Unit tests for llms.txt generator - happy path only."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("FIRECRAWL_API_KEY", "test-key")

from dataclasses import dataclass

from app.jobs.generator import generate_all_files


@dataclass
class MockJob:
    """Mock job object for testing."""

    url: str
    site_title: str | None = None
    site_summary: str | None = None
    site_notes: str | None = None
    discovered_categories: list[str] | None = None


@dataclass
class MockPage:
    """Mock page object for testing."""

    url: str
    title: str | None = None
    summary: str | None = None
    included: bool = True
    category: str | None = None
    importance_score: int = 50
    markdown: str | None = None


def test_generate_all_files_produces_valid_output():
    """Verify generate_all_files produces all 3 file types with correct content."""
    job = MockJob(
        url="https://example.com",
        site_title="Example",
        site_summary="A test site",
    )
    pages = [
        MockPage(
            url="https://example.com/docs",
            title="Docs",
            summary="Doc summary",
            category="Docs",
            markdown="# Documentation\n\nContent here.",
        ),
        MockPage(
            url="https://example.com/api",
            title="API",
            summary="API summary",
            category="API",
            markdown="# API Reference\n\nEndpoints.",
        ),
    ]

    result = generate_all_files(job, pages)

    # Both file types should be present
    assert "llms_txt" in result
    assert "llms_ctx" in result

    # llms_txt should have markdown format with categories (Title Case)
    assert "# Example" in result["llms_txt"]
    assert "## Docs" in result["llms_txt"]
    assert "## API" in result["llms_txt"]
    assert "[Docs]" in result["llms_txt"]

    # llms_ctx should have XML structure
    assert "<project" in result["llms_ctx"]
    assert "<docs>" in result["llms_ctx"]
    assert "</project>" in result["llms_ctx"]


def test_generate_llms_txt_includes_important_notes_header():
    """Verify 'Important notes:' header appears when site_notes exist."""
    job = MockJob(
        url="https://example.com",
        site_title="Example Product",
        site_summary="A test product for testing",
        site_notes="- This is not compatible with React\n- Requires Python 3.10+",
    )
    pages = [
        MockPage(
            url="https://example.com/docs",
            title="Getting Started",
            summary="A brief overview of Example Product features",
            category="Docs",
            markdown="# Getting Started\n\nContent here.",
        ),
    ]

    result = generate_all_files(job, pages)

    # Should have "Important notes:" header before the notes
    assert "Important notes:" in result["llms_txt"]
    assert "- This is not compatible with React" in result["llms_txt"]

    # Verify the notes come after the header
    txt = result["llms_txt"]
    header_pos = txt.find("Important notes:")
    notes_pos = txt.find("- This is not compatible with React")
    assert header_pos < notes_pos


def test_generate_llms_txt_link_format():
    """Verify link format is '- [Title](url): Description'."""
    job = MockJob(
        url="https://example.com",
        site_title="Test",
        site_summary="Test site",
    )
    pages = [
        MockPage(
            url="https://example.com/guide",
            title="Quick Start Guide",
            summary="Step-by-step guide to get started with the product",
            category="Docs",
            markdown="# Guide\n\nContent.",
        ),
    ]

    result = generate_all_files(job, pages)

    # Verify link format: "- [Title](url): Description"
    assert "- [Quick Start Guide](https://example.com/guide): Step-by-step guide" in result["llms_txt"]
