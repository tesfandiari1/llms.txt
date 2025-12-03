"""llms.txt file generation.

Generates two output variants per the llms.txt specification (https://llmstxt.org/):
- llms.txt: Links with descriptions, grouped by category
- llms-ctx.txt: XML structure with embedded markdown content

Output format follows the spec:
```
# ProductName

> Product description explaining what it IS and DOES.

Important notes:

- What the product is NOT or limitations
- Compatibility notes

## Docs

- [Page Title](url): Description of what this page contains

## Optional

- [Less Essential](url): Description
```
"""

from urllib.parse import urlparse


def generate_all_files(job, pages: list) -> dict:
    """
    Generate all three llms.txt variants.

    Args:
        job: Job object with site_title, site_summary, site_notes, url
        pages: List of Page objects with title, url, summary, category,
               importance_score, markdown, included

    Returns:
        Dict with keys: llms_txt, llms_ctx
    """
    # Group pages by category
    by_category = {}
    for page in pages:
        cat = page.category or "Optional"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(page)

    return {
        "llms_txt": generate_llms_txt(job, by_category),
        "llms_ctx": generate_llms_ctx(job, by_category),
    }


def generate_llms_txt(job, by_category: dict) -> str:
    """
    Generate the base llms.txt file with links and descriptions.

    Format per spec:
    ```
    # Title

    > Summary sentence.

    Important notes:

    - Note 1
    - Note 2

    ## Category

    - [Page Title](url): Description
    ```
    """
    site_title = job.site_title
    site_summary = job.site_summary
    site_notes = job.site_notes

    # Fallback title from domain if not set
    if not site_title:
        domain = _extract_domain(job.url)
        site_title = domain.replace(".", " ").title()

    # Fallback summary if not set
    if not site_summary:
        domain = _extract_domain(job.url)
        site_summary = f"Documentation for {domain}"

    lines = [
        f"# {site_title}",
        "",
        f"> {site_summary}",
        "",
    ]

    # Add "Important notes:" section if notes exist
    if site_notes and site_notes.strip():
        lines.append("Important notes:")
        lines.append("")
        # site_notes should already be formatted as bullet points from the LLM
        # But ensure each line is a bullet point
        for note in site_notes.strip().split("\n"):
            stripped = note.strip()
            if stripped:
                # Ensure it starts with "- " for consistency
                formatted = stripped if stripped.startswith("- ") else f"- {stripped}"
                lines.append(formatted)
        lines.append("")

    has_content = False

    # Use discovered categories (already in correct order) or fall back to alphabetical
    category_order = job.discovered_categories or sorted(by_category.keys())

    for cat in category_order:
        if cat not in by_category:
            continue

        pages = by_category[cat]
        if not pages:
            continue

        # Filter to included pages with summaries
        included_pages = [p for p in pages if p.included and p.summary]

        if not included_pages:
            continue

        has_content = True

        # Ensure category name is Title Case
        category_display = _title_case_category(cat)
        lines.append(f"## {category_display}")
        lines.append("")

        # Sort by importance score (highest first)
        sorted_pages = sorted(included_pages, key=lambda p: -(p.importance_score or 50))

        for page in sorted_pages:
            title = page.title or "Untitled"
            url = page.url
            summary = page.summary or ""

            safe_title = _escape_markdown_link(title)
            safe_summary = _truncate_summary(summary)

            # Format: "- [Title](url): Description"
            lines.append(f"- [{safe_title}]({url}): {safe_summary}")

        lines.append("")

    if not has_content:
        lines.append("*No documentation pages available.*")
        lines.append("")

    return "\n".join(lines)


def generate_llms_ctx(job, by_category: dict) -> str:
    """
    Generate llms-ctx.txt with embedded markdown content in XML structure.

    Args:
        job: Job object with site_title, site_summary, site_notes, url
        by_category: Dict mapping category name to list of pages

    Returns:
        llms-ctx.txt content as string
    """
    site_title = job.site_title
    site_summary = job.site_summary
    site_notes = job.site_notes

    if not site_title:
        domain = _extract_domain(job.url)
        site_title = domain.replace(".", " ").title()

    if not site_summary:
        domain = _extract_domain(job.url)
        site_summary = f"Documentation for {domain}"

    # Escape quotes in attributes
    safe_title = site_title.replace('"', "&quot;")
    safe_summary = site_summary.replace('"', "&quot;")

    lines = [f'<project title="{safe_title}" summary="{safe_summary}">']

    if site_notes and site_notes.strip():
        lines.append("<notes>")
        lines.append(site_notes)
        lines.append("</notes>")

    # Use discovered categories or fall back to alphabetical
    category_order = job.discovered_categories or sorted(by_category.keys())

    for cat in category_order:
        if cat not in by_category:
            continue

        # Filter to included pages with markdown content
        cat_pages = [p for p in by_category[cat] if p.included and p.markdown]

        if not cat_pages:
            continue

        # Convert category to XML-safe tag (lowercase, hyphenated)
        tag = cat.lower().replace(" ", "-")
        lines.append(f"<{tag}>")

        # Sort by importance score (highest first)
        sorted_pages = sorted(cat_pages, key=lambda p: -(p.importance_score or 50))

        for page in sorted_pages:
            title = page.title or "Untitled"
            summary = page.summary or ""
            markdown = page.markdown or ""

            # Escape quotes in attributes
            safe_page_title = title.replace('"', "&quot;")
            safe_page_desc = summary.replace('"', "&quot;")

            lines.append(f'<doc title="{safe_page_title}" desc="{safe_page_desc}">')
            lines.append(markdown)
            lines.append("</doc>")

        lines.append(f"</{tag}>")

    lines.append("</project>")

    return "\n".join(lines)


# =============================================================================
# Helper functions
# =============================================================================


def _extract_domain(url: str) -> str:
    """Extract domain from URL, stripping www. prefix."""
    if not url:
        return "Unknown Site"
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path.split("/")[0]
    if not domain:
        return "Unknown Site"
    return domain[4:] if domain.startswith("www.") else domain


def _escape_markdown_link(text: str) -> str:
    """Escape characters that would break markdown links."""
    # Only escape brackets which break link syntax
    return text.replace("[", "\\[").replace("]", "\\]")


def _title_case_category(category: str) -> str:
    """
    Ensure category name is in Title Case.

    Examples:
    - "docs" -> "Docs"
    - "api reference" -> "API Reference"
    - "API" -> "API" (preserve all-caps)
    - "getting-started" -> "Getting Started"
    """
    # Handle already correct cases
    if category in ("API", "API Reference", "Docs", "Examples", "Optional"):
        return category

    # Handle common variations
    lower = category.lower()
    if lower == "api":
        return "API"
    if lower == "api reference":
        return "API Reference"
    if lower == "api-reference":
        return "API Reference"

    # General case: title case with hyphen/space handling
    words = category.replace("-", " ").split()
    return " ".join(word.capitalize() for word in words)


def _truncate_summary(summary: str, max_length: int = 200) -> str:
    """Truncate summary at word boundary if too long."""
    if len(summary) <= max_length:
        return summary
    truncated = summary[:max_length]
    last_space = truncated.rfind(" ")
    if last_space > max_length // 2:
        truncated = truncated[:last_space]
    return truncated.rstrip() + "..."
