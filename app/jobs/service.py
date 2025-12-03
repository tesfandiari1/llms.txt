"""Job processing business logic."""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.jobs import repository as repo
from app.jobs.categorizer import filter_junk_urls, merge_llm_categorization
from app.jobs.firecrawl import FirecrawlClient
from app.jobs.generator import generate_all_files
from app.jobs.models import Job
from app.jobs.schemas import JobStatus
from app.llm.summarizer import Summarizer
from app.logging import job_context
from app.storage import Storage

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    """Normalize URL for matching (strip trailing slash, force https)."""
    url = url.rstrip("/")
    if url.startswith("http://"):
        url = "https://" + url[7:]
    return url.lower()


class JobService:
    """Orchestrates the 5-phase job processing pipeline."""

    def __init__(
        self,
        db: Session,
        firecrawl: FirecrawlClient,
        summarizer: Summarizer,
        storage: Storage,
    ):
        self.db = db
        self.firecrawl = firecrawl
        self.summarizer = summarizer
        self.storage = storage

    def process_job(self, job_id: UUID) -> None:
        """
        Main 5-phase pipeline.

        Phases:
        1. Discovery (5-10%) - Find pages via Firecrawl /map
        2. Categorization (10-15%) - Categorize URLs, create Page records
        3. Extraction (15-50%) - Scrape each page
        4. Summarization (50-90%) - LLM summaries + site summary
        5. Generation (90-100%) - Create all llms.txt variants
        """
        job_context.set(str(job_id))

        job = repo.get_job(self.db, job_id)
        if not job:
            msg = f"Job {job_id} not found"
            raise ValueError(msg)

        try:
            self._discover(job)
            self._categorize(job)

            if job.mode == "scan":
                repo.update_job(
                    self.db,
                    job.id,
                    status=JobStatus.COMPLETED,
                    progress_percent=100,
                    progress_message="Scan complete",
                )
                logger.info(f"Job {job_id} scan complete")
                return

            self._extract(job)

            if job.auto_generate:
                self._summarize(job)
                self._generate(job)
            else:
                repo.update_job(
                    self.db,
                    job.id,
                    status=JobStatus.COMPLETED,
                    progress_percent=100,
                    progress_message="Extraction complete",
                )

            logger.info(f"Job {job_id} completed")

        except Exception as e:
            logger.exception(f"Job {job_id} failed")
            repo.update_job(
                self.db, job.id, status=JobStatus.FAILED, error_message=str(e)
            )
            raise  # Re-raise so pgqueuer knows it failed

    def continue_generation(self, job_id: UUID) -> None:
        """For scan-only jobs that want to generate later."""
        job_context.set(str(job_id))

        job = repo.get_job(self.db, job_id)
        if not job:
            msg = f"Job {job_id} not found"
            raise ValueError(msg)

        if job.status != JobStatus.SUMMARIZING or job.auto_generate:
            msg = (
                f"Job {job_id} not eligible for continue_generation: "
                f"status={job.status}, auto_generate={job.auto_generate}"
            )
            raise ValueError(msg)

        try:
            repo.update_job(
                self.db,
                job.id,
                status=JobStatus.EXTRACTING,
                progress_percent=15,
                progress_message="Extracting content...",
            )

            self._extract(job)
            self._summarize(job)
            self._generate(job)

            logger.info(f"Job {job_id} generation completed")

        except Exception as e:
            logger.exception(f"Job {job_id} continue_generation failed")
            repo.update_job(
                self.db, job.id, status=JobStatus.FAILED, error_message=str(e)
            )
            raise

    def _discover(self, job: Job) -> None:
        """Phase 1: Discover pages on the site."""
        repo.update_job(
            self.db,
            job.id,
            status=JobStatus.DISCOVERING,
            progress_percent=5,
            progress_message="Discovering pages...",
        )

        urls = self.firecrawl.map_site(job.url)
        logger.info(f"Job {job.id}: Discovered {len(urls)} URLs")

        # Store URLs in JSONB - don't create Page records yet
        repo.update_job(
            self.db,
            job.id,
            discovered_urls=urls,
            progress_percent=10,
        )

    def _categorize(self, job: Job) -> None:
        """Phase 2: Filter junk URLs, then LLM categorization."""
        repo.update_job(
            self.db,
            job.id,
            status=JobStatus.CATEGORIZING,
            progress_percent=10,
            progress_message="Categorizing pages...",
        )

        urls = job.discovered_urls or []
        if not urls:
            msg = f"Job {job.id}: No URLs discovered"
            raise ValueError(msg)

        filtered_urls = filter_junk_urls(urls, job.url)
        if not filtered_urls:
            msg = f"Job {job.id}: All URLs filtered out"
            raise ValueError(msg)

        logger.info(
            f"Job {job.id}: Filtered to {len(filtered_urls)} URLs "
            f"(from {len(urls)} discovered)"
        )

        result = self.summarizer.categorize_urls(job.url, filtered_urls)
        categories = result.get("categories", [])
        categorized = merge_llm_categorization(result)

        repo.create_pages_from_categorization(self.db, job.id, categorized)
        repo.update_job(
            self.db,
            job.id,
            discovered_categories=categories,
            pages_total=len(categorized),
            progress_percent=15,
            progress_message=f"Categorized {len(categorized)} pages",
        )

        logger.info(f"Job {job.id}: {len(categories)} categories, {len(categorized)} pages")

    def _extract(self, job: Job) -> None:
        """Phase 3: Extract content from all pages using batch scraping."""
        repo.update_job(
            self.db,
            job.id,
            status=JobStatus.EXTRACTING,
            progress_percent=15,
            progress_message="Extracting content...",
        )

        pages = repo.get_pages_for_extraction(self.db, job.id)
        total = len(pages)

        if total == 0:
            msg = f"Job {job.id}: No included pages to extract"
            raise ValueError(msg)

        urls = [page.url for page in pages]
        results = self.firecrawl.batch_scrape(urls)

        # Build map using URL for matching
        url_to_result = {_normalize_url(r.get("url", "")): r for r in results}

        extracted_count = 0
        empty_markdown_count = 0

        for page in pages:
            result = url_to_result.get(_normalize_url(page.url), {})
            markdown = result.get("markdown", "")
            title = result.get("title", "")
            word_count = len(markdown.split()) if markdown else 0

            if not markdown:
                empty_markdown_count += 1

            if not title:
                logger.warning(f"Page {page.url} has no title after extraction")

            repo.update_page(
                self.db,
                page.id,
                title=title,
                markdown=markdown,
                word_count=word_count,
                extraction_status="success" if markdown else "failed",
            )

            if markdown:
                extracted_count += 1

        repo.update_job(
            self.db,
            job.id,
            progress_percent=50,
            progress_message=f"Extracted {extracted_count}/{total} pages",
            pages_processed=total,
        )

        logger.info(
            f"Job {job.id}: Extracted {extracted_count}/{total} pages. "
            f"{empty_markdown_count} pages returned empty markdown."
        )

    def _summarize(self, job: Job) -> None:
        """Phase 4: Summarize pages with LLM and generate site summary."""
        repo.update_job(
            self.db,
            job.id,
            status=JobStatus.SUMMARIZING,
            progress_percent=50,
            progress_message="Summarizing pages...",
        )

        pages = repo.get_pages_with_content(self.db, job.id)
        if not pages:
            msg = f"Job {job.id}: No pages with content to summarize"
            raise ValueError(msg)

        batch_input = [
            {
                "id": str(page.id),
                "title": page.title or "",
                "markdown": page.markdown or "",
            }
            for page in pages
        ]

        results = self.summarizer.summarize_batch(batch_input, max_workers=5)

        for result in results:
            summary = result.get("summary", "")
            repo.update_page(
                self.db,
                UUID(result["id"]),
                summary=summary,
                summarization_status="success" if summary else "failed",
            )

        # Site summary from top pages by importance
        top_pages = sorted(pages, key=lambda p: -p.importance_score)[:5]
        top_pages_data = [
            {"title": p.title or "", "markdown": p.markdown or ""} for p in top_pages
        ]

        site_summary = self.summarizer.generate_site_summary(job.url, top_pages_data)
        site_notes = site_summary.get("notes", [])
        notes_text = "\n".join(site_notes) if isinstance(site_notes, list) else site_notes

        repo.update_job(
            self.db,
            job.id,
            site_title=site_summary.get("title"),
            site_summary=site_summary.get("summary"),
            site_notes=notes_text if notes_text else None,
            progress_percent=90,
            progress_message=f"Summarized {len(results)} pages",
        )

        logger.info(f"Job {job.id}: Summarized {len(results)} pages, site: {site_summary.get('title')}")

    def _generate(self, job: Job) -> None:
        """Phase 5: Generate all llms.txt file variants."""
        repo.update_job(
            self.db,
            job.id,
            progress_percent=90,
            progress_message="Generating llms.txt files...",
        )

        pages = repo.get_included_pages_for_generation(self.db, job.id)

        # Need fresh job data for site_title, site_summary, site_notes set in _summarize
        self.db.refresh(job)

        files = generate_all_files(job, pages)

        result_files = {}
        for file_key, content in files.items():
            filename = file_key.replace("_", "-").replace("llms-txt", "llms") + ".txt"
            storage_key = f"{job.id}/{filename}"
            self.storage.save(storage_key, content)
            result_files[file_key] = storage_key

        repo.update_job(
            self.db,
            job.id,
            status=JobStatus.COMPLETED,
            progress_percent=100,
            progress_message="Complete",
            result_files=result_files,
        )

        logger.info(f"Job {job.id}: Generated {list(result_files.keys())}")
