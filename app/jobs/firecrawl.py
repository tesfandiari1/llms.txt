"""Firecrawl API client for site mapping and page scraping."""

import logging

from firecrawl import Firecrawl

logger = logging.getLogger(__name__)


class FirecrawlClient:
    """Client for Firecrawl API - thin wrapper around the SDK."""

    def __init__(self, api_key: str):
        self.client = Firecrawl(api_key=api_key)

    def map_site(self, url: str, limit: int = 500) -> list[str]:
        """Discover all URLs on a site."""
        logger.info(f"Mapping site: {url}")
        result = self.client.map(url=url, limit=limit)

        # Extract URL strings from LinkResult objects
        raw_links = result.links if hasattr(result, "links") else result
        urls = [getattr(link, "url", str(link)) for link in raw_links]

        logger.info(f"Discovered {len(urls)} URLs")
        return urls

    def batch_scrape(self, urls: list[str]) -> list[dict]:
        """Scrape multiple pages. SDK handles polling automatically."""
        if not urls:
            return []

        logger.info(f"Batch scraping {len(urls)} URLs")

        result = self.client.batch_scrape(
            urls,
            formats=["markdown"],
            only_main_content=True,
            wait_for=3000,
        )

        logger.info(
            f"Batch complete: {getattr(result, 'completed', '?')}/{getattr(result, 'total', len(urls))}"
        )

        # Convert SDK Document objects to dicts (order not guaranteed)
        return [self._to_dict(doc) for doc in result.data]

    def _to_dict(self, doc) -> dict:
        """Convert SDK Document to dict."""
        meta = getattr(doc, "metadata", None)
        return {
            "url": getattr(meta, "source_url", "") if meta else "",
            "title": getattr(meta, "title", "") if meta else "",
            "markdown": getattr(doc, "markdown", "") or "",
        }
