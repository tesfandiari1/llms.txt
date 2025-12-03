"""LLM prompts for llms.txt generation.

These prompts are designed to produce output that matches the llms.txt specification:
https://llmstxt.org/

Key principles:
- Title should be the product name, not the domain
- Summary should explain what the product IS and DOES
- Notes should clarify what the product ISN'T (prevent LLM confusion)
- Categories use Title Case: "Docs", "API Reference", "Examples", "Optional"
- Link descriptions focus on LLM usefulness, not generic summaries

Prompt design uses Anthropic best practices:
- XML tags to clearly separate content from instructions
- Scratchpad sections for reasoning before output
- Explicit grounding in provided content only
"""

SUMMARIZE_PAGE = """You are helping create an llms.txt file - a standardized way to provide documentation context to LLMs. Your task is to write a brief description of a documentation page that helps an LLM understand when to reference it.

Here is the documentation page content:

<page_content>
{page_content}
</page_content>

Your description should be 10-25 words and help an LLM understand:
- What specific information this page contains
- When an LLM should reference this page

Focus on the practical value for an LLM trying to answer questions about this product/library. Be specific about the content rather than generic.

Bad examples (too generic):
- "Documentation for the API"
- "Learn how to get started"
- "Reference guide for developers"

Good examples (LLM-useful):
- "A brief overview of many FastHTML features"
- "Detailed walk-thru of a complete CRUD app showing idiomatic use of FastHTML and HTMX patterns"
- "Brief description of all HTMX attributes, CSS classes, headers, events, extensions, and config options"
- "Step-by-step guide to accept your first payment with Stripe Checkout"

Write ONLY the description, nothing else. Do not include quotes around your response."""

GENERATE_SITE_SUMMARY = """You are creating the header section for an llms.txt file - a standardized format that helps LLMs understand a project's documentation structure and content.

You will be analyzing documentation pages from a website to extract key information. Here is the site URL:

<site_url>
{site_url}
</site_url>

Here are sample pages from the documentation:

<sample_pages>
{sample_pages}
</sample_pages>

Your task is to analyze these pages and generate three pieces of information:

**1. Title**
Extract the official product or project name. This should be:
- The actual product/library/service name (e.g., "FastHTML", "Stripe API", "React Router", "PostgreSQL")
- NOT the domain name (e.g., NOT "docs.stripe.com")
- NOT a page heading like "Welcome to X" or "The X Documentation"
- The name as the creators refer to their own product

**2. Summary**
Write a single, clear sentence of 20-40 words that explains:
- What this product/library/service IS (its category/type)
- What it DOES (its main purpose or function)
- Key technologies it uses, integrates with, or builds upon (if relevant and important)

Example: "FastHTML is a python library which brings together Starlette, Uvicorn, HTMX, and fastcore's FT 'FastTags' into a library for creating server-rendered hypermedia applications."

**3. Notes**
Provide 2-4 bullet points (each 10-30 words) that clarify important information to prevent LLM confusion. Focus on:
- What this is NOT (common misconceptions, similar-sounding products it differs from)
- Compatibility limitations or requirements (what it works/doesn't work with)
- Key architectural decisions or constraints that affect how it should be used
- Important scope limitations (what it's not designed for)

Examples of good notes:
- "Although parts of its API are inspired by FastAPI, it is *not* compatible with FastAPI syntax and is not targeted at creating API services"
- "FastHTML is compatible with JS-native web components and any vanilla JS library, but not with React, Vue, or Svelte"
- "All API requests must be made over HTTPS; calls made over HTTP will fail"

Before providing your final answer, use the scratchpad to think through your analysis:

<scratchpad>
- Identify the product name by looking for consistent references across pages
- Determine the product category and main purpose
- Note any key technologies mentioned repeatedly
- Identify potential points of confusion or common misconceptions
- List compatibility information and limitations
</scratchpad>

After your analysis, provide your response in this exact JSON format:

<answer>
{{"title": "...", "summary": "...", "notes": ["...", "...", "..."]}}
</answer>

Ensure the JSON is valid and properly formatted with double quotes around all strings."""

CATEGORIZE_URLS = """You are organizing documentation URLs into categories for an llms.txt file. Your task is to analyze a list of URLs from a documentation site and group them into logical categories with importance scores.

Here is the site you're analyzing:
<site_url>
{site_url}
</site_url>

Here are the URLs to categorize:
<urls_list>
{urls_list}
</urls_list>

The llms.txt specification uses these standard category patterns:
- "Docs" - Main documentation, guides, tutorials, getting started content
- "API" or "API Reference" - API documentation, endpoint references, SDK docs
- "Examples" - Code examples, sample applications, tutorials with code
- "Optional" - Less essential docs (changelogs, contributing guides, advanced topics)

Your categorization should follow these rules:

CATEGORY SELECTION:
- Create 2-5 categories total (not more, not fewer)
- Prefer the standard category names listed above when they fit
- Use site-specific category names only if they're clearer (e.g., "Payments", "Authentication", "Webhooks")
- Use Title Case for all category names
- The first category should be the most important entry point (usually "Docs" or "Getting Started")
- If you use "Optional", it must be the last category
- Order categories from most essential to least essential

IMPORTANCE SCORING:
- Assign each URL an importance score from 0-100
- Higher scores = more essential for understanding the product
- Getting started guides, core concepts: 90-100
- Main feature documentation: 70-90
- API references, specific endpoints: 60-80
- Examples and tutorials: 50-70
- Advanced topics: 40-60
- Changelogs, contributing guides, misc: 10-40

ASSIGNMENT RULES:
- Every URL must be assigned to exactly one category
- No URL should be left uncategorized
- No URL should appear in multiple categories

Before providing your final answer, use a scratchpad to think through your analysis:

<scratchpad>
- Examine the URLs and identify common themes
- Determine which URLs are most essential (entry points, core docs)
- Decide on 2-5 appropriate categories
- Plan the ordering of categories from most to least essential
- Consider the importance score for each URL
</scratchpad>

After your analysis, provide your response as valid JSON only. Do not include any text before or after the JSON. Use this exact format:

{{
  "categories": ["Category One", "Category Two", "Category Three"],
  "pages": [
    {{"url": "https://example.com/page1", "category": "Category One", "importance": 95}},
    {{"url": "https://example.com/page2", "category": "Category Two", "importance": 80}},
    {{"url": "https://example.com/page3", "category": "Category One", "importance": 75}}
  ]
}}

Remember: Output only valid JSON. The "categories" array should list categories in order from most to least essential. Every URL from the input must appear exactly once in the "pages" array."""
