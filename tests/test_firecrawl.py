"""Unit tests for FirecrawlClient - happy paths only."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("FIRECRAWL_API_KEY", "test-key")

from unittest.mock import MagicMock, patch

from app.jobs.firecrawl import FirecrawlClient


def test_map_site_returns_urls():
    """map_site returns list of discovered URLs."""
    with patch("app.jobs.firecrawl.Firecrawl") as mock_firecrawl_cls:
        mock_client = MagicMock()
        mock_firecrawl_cls.return_value = mock_client
        # v4.x SDK returns list of strings directly
        mock_client.map.return_value = [
            "https://example.com/page1",
            "https://example.com/page2",
        ]

        client = FirecrawlClient(api_key="test-key")
        urls = client.map_site("https://example.com")

        assert urls == ["https://example.com/page1", "https://example.com/page2"]
        mock_client.map.assert_called_once()


def test_batch_scrape_returns_documents():
    """batch_scrape returns list of scraped documents with markdown."""
    with patch("app.jobs.firecrawl.Firecrawl") as mock_firecrawl_cls:
        mock_client = MagicMock()
        mock_firecrawl_cls.return_value = mock_client
        mock_client.batch_scrape.return_value = {
            "status": "completed",
            "data": [
                {
                    "markdown": "# Page 1",
                    "metadata": {
                        "title": "Page 1",
                        "sourceURL": "https://example.com/page1",
                    },
                },
                {
                    "markdown": "# Page 2",
                    "metadata": {
                        "title": "Page 2",
                        "sourceURL": "https://example.com/page2",
                    },
                },
            ],
        }

        client = FirecrawlClient(api_key="test-key")
        results = client.batch_scrape(
            ["https://example.com/page1", "https://example.com/page2"]
        )

        assert len(results) == 2  # noqa: PLR2004
        assert results[0]["markdown"] == "# Page 1"
        assert results[1]["metadata"]["title"] == "Page 2"
