"""Database operations for jobs and pages."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.jobs.models import Job, Page


def get_job(db: Session, job_id: UUID) -> Job | None:
    """Fetch a job by ID."""
    return db.query(Job).filter(Job.id == job_id).first()


def update_job(db: Session, job_id: UUID, **kwargs) -> None:
    """
    Update job fields.

    Supports all fields including: status, progress_percent, progress_message,
    pages_total, pages_processed, discovered_urls, site_title, site_summary,
    site_notes, result_files, error_message.
    """
    db.query(Job).filter(Job.id == job_id).update(kwargs)
    db.commit()


def create_pages_from_categorization(
    db: Session, job_id: UUID, categorized: list[dict]
) -> list[Page]:
    """
    Create Page records from categorization results.

    Args:
        db: Database session
        job_id: Job UUID
        categorized: List of dicts from categorize_urls() with keys:
            url, path, category, importance_score, included

    Returns:
        List of created Page objects
    """
    pages = [
        Page(
            job_id=job_id,
            url=item["url"],
            path=item.get("path"),
            category=item.get("category", "optional"),
            importance_score=item.get("importance_score", 50),
            included=item.get("included", True),
        )
        for item in categorized
    ]
    db.add_all(pages)
    db.commit()
    return pages


def get_pages(db: Session, job_id: UUID) -> list[Page]:
    """Fetch all pages for a job."""
    return db.query(Page).filter(Page.job_id == job_id).all()


def get_pages_for_extraction(db: Session, job_id: UUID) -> list[Page]:
    """
    Get pages that should be extracted (included=True).

    Used in extraction phase before markdown exists.
    """
    return (
        db.query(Page)
        .filter(Page.job_id == job_id, Page.included.is_(True))
        .all()
    )


def get_pages_with_content(db: Session, job_id: UUID) -> list[Page]:
    """
    Get pages that have been extracted and are included.

    Returns pages where:
    - included=True (user selected)
    - markdown IS NOT NULL and NOT empty (successfully extracted)

    Used in summarization phase.
    """
    return (
        db.query(Page)
        .filter(
            Page.job_id == job_id,
            Page.included.is_(True),
            Page.markdown.isnot(None),
            Page.markdown != "",
        )
        .all()
    )


def get_included_pages_for_generation(db: Session, job_id: UUID) -> list[Page]:
    """
    Fetch pages suitable for llms.txt generation.

    Returns pages where:
    - included=True
    - markdown is not None and not empty

    Unsorted - caller (generator) handles ordering via job.discovered_categories.
    """
    return (
        db.query(Page)
        .filter(
            Page.job_id == job_id,
            Page.included.is_(True),
            Page.markdown.isnot(None),
            Page.markdown != "",
        )
        .all()
    )


def update_page(db: Session, page_id: UUID, **kwargs) -> None:
    """Update page fields."""
    db.query(Page).filter(Page.id == page_id).update(kwargs)
    db.commit()
