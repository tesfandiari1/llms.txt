"""LLM-based page summarization using Anthropic Claude."""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import anthropic
from anthropic import Timeout

from app.config import settings
from app.llm.prompts import CATEGORIZE_URLS, GENERATE_SITE_SUMMARY, SUMMARIZE_PAGE

logger = logging.getLogger(__name__)

# Minimum words for content to be worth summarizing
MIN_CONTENT_WORDS = 20


def extract_json(text: str) -> str:
    """
    Extract JSON from LLM response, handling markdown code blocks.

    Claude often wraps JSON in ```json ... ``` blocks. This strips them.
    """
    # Try to find JSON in markdown code block
    code_block_pattern = r"```(?:json)?\s*([\s\S]*?)```"
    match = re.search(code_block_pattern, text)
    if match:
        return match.group(1).strip()

    # Return as-is if no code block found
    return text.strip()


def extract_answer(text: str) -> str:
    """
    Extract content from <answer> tags used in scratchpad prompts.

    The scratchpad pattern has the model output reasoning first,
    then provide the final answer in <answer> tags.
    """
    match = re.search(r"<answer>([\s\S]*?)</answer>", text)
    if match:
        return match.group(1).strip()

    # Fall back to extract_json if no answer tags found
    return extract_json(text)


class Summarizer:
    """Summarizes documentation pages using Claude Haiku and generates site summaries."""

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        model_advanced: str | None = None,
    ):
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=5)
        self.model = model or settings.anthropic_model
        self.model_advanced = model_advanced or settings.anthropic_model_advanced

    def summarize_page(self, title: str, markdown: str) -> str:
        """
        Generate a 10-25 word description for llms.txt entry.

        Uses Claude Haiku for cost efficiency (~$0.00025 per page).

        Args:
            title: The page title
            markdown: The page content in markdown format

        Returns:
            A 10-25 word summary, or empty string on failure
        """
        # Skip pages with no content or too little content - don't waste LLM calls
        if not markdown or not markdown.strip():
            logger.warning(f"Skipping summarization for '{title}': no content")
            return ""

        word_count = len(markdown.split())
        if word_count < MIN_CONTENT_WORDS:
            logger.warning(
                f"Skipping summarization for '{title}': too short ({word_count} words)"
            )
            return ""

        # Truncate content to avoid token limits
        content = markdown[:8000]

        # Format content with XML tags for clear separation
        page_content = f"Title: {title}\n\nContent:\n{content}"
        prompt = SUMMARIZE_PAGE.format(page_content=page_content)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}],
                timeout=Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
            )
            summary = response.content[0].text.strip()
            logger.debug(f"Summarized '{title}': {summary[:50]}...")
            return summary

        except anthropic.APIError as e:
            logger.error(f"API error summarizing '{title}': {e}")
            return ""
        except Exception as e:
            logger.error(f"Unexpected error summarizing '{title}': {e}")
            return ""

    def generate_site_summary(self, site_url: str, top_pages: list[dict]) -> dict:
        """
        Generate site-level summary and title for llms.txt header.

        Uses Claude Sonnet for better quality (~$0.003 per call).

        Args:
            site_url: The base URL of the site
            top_pages: List of dicts with 'title' and 'markdown' keys
                       (top 5 most important pages will be used)

        Returns:
            Dict with keys: title, summary, notes
            On failure, returns sensible defaults
        """
        # Filter to pages that actually have content
        pages_with_content = [
            p for p in top_pages[:5]
            if p.get("markdown") and p["markdown"].strip()
        ]

        if not pages_with_content:
            logger.warning(f"No pages with content for site summary: {site_url}")
            return self._default_site_summary(site_url)

        # Build sample_pages content with XML structure for clear separation
        sample_pages = "\n\n".join([
            f"## {p['title']}\n{p['markdown'][:2000]}"
            for p in pages_with_content
        ])

        prompt = GENERATE_SITE_SUMMARY.format(
            site_url=site_url,
            sample_pages=sample_pages,
        )

        try:
            response = self.client.messages.create(
                model=self.model_advanced,
                max_tokens=1500,  # Increased for scratchpad reasoning
                messages=[{"role": "user", "content": prompt}],
                timeout=Timeout(connect=5.0, read=90.0, write=10.0, pool=5.0),
            )

            raw_text = response.content[0].text
            # Extract from <answer> tags (scratchpad pattern)
            answer_text = extract_answer(raw_text)
            # Also handle any markdown code blocks within the answer
            cleaned = extract_json(answer_text)
            result = json.loads(cleaned)
            logger.info(f"Generated site summary for {site_url}: {result.get('title')}")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse site summary JSON: {e}. Raw: {response.content[0].text[:200]}")
            return self._default_site_summary(site_url)
        except anthropic.APIError as e:
            logger.error(f"API error generating site summary: {e}")
            return self._default_site_summary(site_url)
        except Exception as e:
            logger.error(f"Unexpected error generating site summary: {e}")
            return self._default_site_summary(site_url)

    def _default_site_summary(self, site_url: str) -> dict:
        """Return default site summary when generation fails."""
        domain = urlparse(site_url).netloc or site_url
        return {
            "title": domain,
            "summary": f"Documentation for {domain}",
            "notes": [],
        }

    def categorize_urls(self, site_url: str, urls: list[str]) -> dict:
        """
        Batch categorize URLs using LLM with discovered categories.

        Args:
            site_url: Base site URL for context
            urls: List of URLs to categorize

        Returns:
            {
                "categories": ["Getting Started", "API Reference", ...],
                "pages": [{url, category, importance}, ...]
            }
        """
        if not urls:
            return {"categories": [], "pages": []}

        logger.info(f"Categorizing {len(urls)} URLs for {site_url}")

        # Format URLs list for the prompt
        urls_list = "\n".join(urls)
        prompt = CATEGORIZE_URLS.format(site_url=site_url, urls_list=urls_list)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=6000,  # Increased for scratchpad reasoning
                messages=[{"role": "user", "content": prompt}],
                timeout=Timeout(connect=5.0, read=90.0, write=10.0, pool=5.0),
            )

            raw_text = response.content[0].text

            # The categorize prompt outputs JSON directly after scratchpad
            # Try to find the JSON object in the response
            cleaned = extract_json(raw_text)
            result = json.loads(cleaned)
            categories = result.get("categories", [])
            pages = result.get("pages", [])
            logger.info(f"Discovered {len(categories)} categories, categorized {len(pages)} URLs")
            return {"categories": categories, "pages": pages}

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse categorization JSON: {e}. Raw: {response.content[0].text[:200]}")
            return self._default_categorization(urls)
        except anthropic.APIError as e:
            logger.error(f"API error categorizing URLs: {e}")
            return self._default_categorization(urls)
        except Exception as e:
            logger.error(f"Unexpected error categorizing URLs: {e}")
            return self._default_categorization(urls)

    def _default_categorization(self, urls: list[str]) -> dict:
        """Return default categorization when LLM fails."""
        return {
            "categories": ["Documentation"],
            "pages": [{"url": url, "category": "Documentation", "importance": 50} for url in urls],
        }

    def summarize_batch(
        self, pages: list[dict], max_workers: int = 5
    ) -> list[dict]:
        """
        Summarize multiple pages concurrently.

        Args:
            pages: List of dicts with keys: id, title, markdown
            max_workers: Maximum concurrent API calls

        Returns:
            Same list with "summary" key added to each dict
        """
        total = len(pages)
        logger.info(f"Starting batch summarization of {total} pages")

        # Create a mapping of future -> page for tracking
        def process_page(page: dict) -> dict:
            summary = self.summarize_page(page["title"], page["markdown"])
            return {**page, "summary": summary}

        results = []
        completed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_page, page): page for page in pages}

            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                    completed += 1
                    logger.info(f"Summarized {completed}/{total} pages")
                except Exception as e:
                    page = futures[future]
                    logger.error(f"Failed to summarize page {page.get('id')}: {e}")
                    results.append({**page, "summary": ""})
                    completed += 1

        # Maintain original order by sorting by id
        page_order = {page["id"]: i for i, page in enumerate(pages)}
        results.sort(key=lambda x: page_order[x["id"]])

        success_count = sum(1 for r in results if r.get("summary"))
        logger.info(
            f"Batch summarization complete: {success_count}/{total} succeeded, "
            f"{total - success_count} failed"
        )
        return results
