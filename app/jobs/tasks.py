"""pgqueuer task definitions - thin wrappers that delegate to service.

Pipeline Phases:
    1. Discovery (5-10%) - Firecrawl /map to find all URLs
    2. Categorization (10-15%) - Local URL analysis, create Page records
    3. Extraction (15-50%) - Firecrawl batch scrape for markdown
    4. Summarization (50-90%) - LLM summaries + site summary
    5. Generation (90-100%) - Create llms.txt, llms-ctx.txt, llms-full.txt

Tasks:
    - process_job: Runs full pipeline (phases 1-5) or stops based on mode
    - continue_generation: Resumes from phase 4 for scan-only jobs
"""

import asyncio
import logging
from uuid import UUID

import asyncpg
from pgqueuer import PgQueuer
from pgqueuer.models import Job as QueueJob
from pgqueuer.queries import Queries

from app.config import settings
from app.database import SessionLocal
from app.jobs.firecrawl import FirecrawlClient
from app.jobs.service import JobService
from app.llm.summarizer import Summarizer
from app.storage import get_storage

logger = logging.getLogger(__name__)


async def _async_enqueue(entrypoint: str, payload: str) -> None:
    """Async helper to enqueue a job."""
    conn = await asyncpg.connect(settings.database_url)
    try:
        queries = Queries.from_asyncpg_connection(conn)
        await queries.enqueue(entrypoint, payload.encode())
    finally:
        await conn.close()


def enqueue_job(entrypoint: str, payload: str) -> None:
    """Synchronously enqueue a job to pgqueuer."""
    asyncio.run(_async_enqueue(entrypoint, payload))


async def create_pgqueuer() -> PgQueuer:
    """Factory function to create configured PgQueuer instance."""
    connection = await asyncpg.connect(settings.database_url)
    pgq = PgQueuer.from_asyncpg_connection(connection)

    @pgq.entrypoint("process_job")
    async def process_job_task(queue_job: QueueJob) -> None:
        """
        Main job processing pipeline - runs all 5 phases.

        Phases executed depend on job configuration:
        - mode='auto': All 5 phases → completed with result_files
        - mode='scan': Phases 1-2 only → completed (user reviews pages)
        - auto_generate=False: Phases 1-3 → completed (user triggers generation)
        """
        job_id = UUID(queue_job.payload.decode())
        logger.info(f"Processing job {job_id}")

        with SessionLocal() as db:
            firecrawl = FirecrawlClient(settings.firecrawl_api_key)
            summarizer = Summarizer(settings.anthropic_api_key)
            storage = get_storage()
            service = JobService(db, firecrawl, summarizer, storage)
            await asyncio.to_thread(service.process_job, job_id)

    @pgq.entrypoint("continue_generation")
    async def continue_generation_task(queue_job: QueueJob) -> None:
        """
        Continue generation for scan-only jobs (phases 3-5).

        Called after user reviews and selects pages. Runs:
        - Phase 3: Extraction (scrape selected pages)
        - Phase 4: Summarization (page summaries + site summary)
        - Phase 5: Generation (llms.txt, llms-ctx.txt, llms-full.txt)

        Requires job to be in completed state with auto_generate=False.
        """
        job_id = UUID(queue_job.payload.decode())
        logger.info(f"Continuing generation for job {job_id}")

        with SessionLocal() as db:
            firecrawl = FirecrawlClient(settings.firecrawl_api_key)
            summarizer = Summarizer(settings.anthropic_api_key)
            storage = get_storage()
            service = JobService(db, firecrawl, summarizer, storage)
            await asyncio.to_thread(service.continue_generation, job_id)

    return pgq
