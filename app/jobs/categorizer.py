"""URL categorization module for llms.txt generation.

Filters junk URLs with regex, transforms LLM categorization results.
"""

import re
from urllib.parse import urlparse

# URLs to always exclude
EXCLUDE_PATTERNS: list[str] = [
    r"/search", r"/login", r"/signup", r"/404", r"/500",
    r"/auth", r"/oauth", r"/callback", r"/privacy", r"/terms",
    r"/tag/", r"/category/", r"/author/", r"/page/\d+",
    r"\?", r"#",  # Query strings and fragments
    r"/sitemap", r"\.xml$",  # Sitemap files
]


def filter_junk_urls(urls: list[str], base_url: str) -> list[str]:
    """
    Remove obvious non-documentation URLs.

    Args:
        urls: List of URLs to filter
        base_url: Base URL (used to filter external URLs)

    Returns:
        Filtered URL list (no categorization)
    """
    base_domain = urlparse(base_url).netloc
    filtered = []

    for url in urls:
        parsed = urlparse(url)

        # Skip external URLs
        if parsed.netloc and parsed.netloc != base_domain:
            continue

        path = parsed.path.lower()

        # Skip junk patterns
        if any(re.search(pattern, path) for pattern in EXCLUDE_PATTERNS):
            continue

        filtered.append(url)

    return filtered


def merge_llm_categorization(llm_results: dict) -> list[dict]:
    """
    Transform LLM output to Page-ready format.

    Args:
        llm_results: LLM output {
            "categories": ["Getting Started", "API Reference", ...],
            "pages": [{url, category, importance}, ...]
        }

    Returns:
        List ready for create_pages_from_categorization():
        [{url, path, category, importance_score, included}, ...]
    """
    categories = llm_results.get("categories", [])
    pages = llm_results.get("pages", [])

    results = []
    for item in pages:
        path = urlparse(item["url"]).path
        results.append({
            "url": item["url"],
            "path": path,
            "category": item.get("category", "Documentation"),
            "importance_score": item.get("importance", 50),
            "included": True,
        })

    # Sort by discovered category order, then importance
    def sort_key(x):
        cat = x["category"]
        cat_index = categories.index(cat) if cat in categories else len(categories)
        return (cat_index, -x["importance_score"])

    results.sort(key=sort_key)

    return results
