"""Unit tests for Summarizer - happy paths only."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("FIRECRAWL_API_KEY", "test-key")

from unittest.mock import MagicMock, patch

from app.llm.summarizer import Summarizer


def test_summarize_page_success():
    """summarize_page returns summary on success."""
    with (
        patch("app.llm.summarizer.anthropic.Anthropic") as mock_anthropic_cls,
        patch("app.llm.summarizer.Timeout"),
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="  This is a summary.  ")]
        mock_client.messages.create.return_value = mock_response

        summarizer = Summarizer(api_key="test-key", model="claude-haiku-4-5")
        result = summarizer.summarize_page("Test Title", "# Content here")

        assert result == "This is a summary."
        mock_client.messages.create.assert_called_once()


def test_summarize_batch_success():
    """summarize_batch processes all pages and returns results."""
    with (
        patch("app.llm.summarizer.anthropic.Anthropic") as mock_anthropic_cls,
        patch("app.llm.summarizer.Timeout"),
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        call_count = [0]

        def mock_create(**kwargs):
            call_count[0] += 1
            response = MagicMock()
            response.content = [MagicMock(text=f"Summary {call_count[0]}")]
            return response

        mock_client.messages.create.side_effect = mock_create

        summarizer = Summarizer(api_key="test-key", model="claude-haiku-4-5")
        pages = [
            {"id": "1", "title": "Page 1", "markdown": "Content 1"},
            {"id": "2", "title": "Page 2", "markdown": "Content 2"},
            {"id": "3", "title": "Page 3", "markdown": "Content 3"},
        ]

        results = summarizer.summarize_batch(pages, max_workers=2)

        assert len(results) == 3  # noqa: PLR2004
        assert results[0]["id"] == "1"
        assert results[1]["id"] == "2"
        assert results[2]["id"] == "3"
        assert all(r["summary"] for r in results)
