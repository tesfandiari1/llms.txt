"""Tests for URL categorization module."""

from app.jobs.categorizer import filter_junk_urls, merge_llm_categorization


def test_filter_junk_urls_removes_excluded_patterns():
    """Verify junk URL filtering."""
    urls = [
        "https://example.com/docs/intro",
        "https://example.com/api/reference",
        "https://external.com/page",  # external - filtered
        "https://example.com/login",  # excluded pattern - filtered
        "https://example.com/search/results",  # excluded pattern - filtered
    ]
    results = filter_junk_urls(urls, "https://example.com")

    assert len(results) == 2  # noqa: PLR2004
    assert "https://example.com/docs/intro" in results
    assert "https://example.com/api/reference" in results
    assert "https://external.com/page" not in results
    assert "https://example.com/login" not in results


def test_merge_llm_categorization_transforms_output():
    """Verify LLM output transformation to Page-ready format."""
    llm_results = {
        "categories": ["Getting Started", "API Reference"],
        "pages": [
            {"url": "https://example.com/docs/intro", "category": "Getting Started", "importance": 90},
            {"url": "https://example.com/api/users", "category": "API Reference", "importance": 80},
        ],
    }
    results = merge_llm_categorization(llm_results)

    assert len(results) == 2  # noqa: PLR2004
    # Check required keys exist
    assert all("url" in r and "category" in r and "included" in r for r in results)
    assert all("path" in r and "importance_score" in r for r in results)
    # Check values
    assert results[0]["url"] == "https://example.com/docs/intro"
    assert results[0]["importance_score"] == 90  # noqa: PLR2004
    assert results[0]["included"] is True
