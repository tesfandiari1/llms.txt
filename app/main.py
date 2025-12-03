from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, init_db
from app.jobs.models import Job, Page
from app.jobs.schemas import (
    GenerateResponse,
    JobCreate,
    JobResponse,
    PageListResponse,
    PageResponse,
    PageUpdateRequest,
    PageUpdateResponse,
)
from app.jobs.tasks import enqueue_job
from app.storage import get_storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db()
    yield


app = FastAPI(title="LLM.txt Generator", version="0.1.0", lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    """Health check endpoint - verifies DB connection."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database connection failed") from None


@app.post("/api/jobs", response_model=JobResponse, status_code=201)
def create_job(data: JobCreate, db: Session = Depends(get_db)):
    """Create a new job and enqueue for processing."""
    job = Job(
        url=str(data.url),
        mode=data.mode,
        auto_generate=data.auto_generate,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Enqueue background processing
    enqueue_job("process_job", str(job.id))

    return JobResponse.model_validate(job)


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    """Get job by ID."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(job)


@app.get("/api/jobs/{job_id}/pages", response_model=PageListResponse)
def get_job_pages(job_id: UUID, db: Session = Depends(get_db)):
    """Get all pages for a job."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    pages = db.query(Page).filter(Page.job_id == job_id).all()

    page_responses = [
        PageResponse(
            id=page.id,
            url=page.url,
            title=page.title,
            category=page.category,
            importance_score=page.importance_score,
            has_markdown=page.markdown is not None,
            has_summary=page.summary is not None,
            included=page.included,
        )
        for page in pages
    ]

    included_count = sum(1 for p in pages if p.included)

    return PageListResponse(
        pages=page_responses,
        total=len(pages),
        included_count=included_count,
    )


@app.patch("/api/jobs/{job_id}/pages", response_model=PageUpdateResponse)
def update_pages(job_id: UUID, data: PageUpdateRequest, db: Session = Depends(get_db)):
    """Update included status for specified pages."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    updated = (
        db.query(Page)
        .filter(Page.job_id == job_id, Page.id.in_(data.page_ids))
        .update({"included": data.included}, synchronize_session=False)
    )
    db.commit()

    return PageUpdateResponse(updated=updated)


@app.post("/api/jobs/{job_id}/generate", response_model=GenerateResponse, status_code=202)
def trigger_generation(job_id: UUID, db: Session = Depends(get_db)):
    """Trigger generation for scan-only jobs."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.auto_generate:
        raise HTTPException(
            status_code=400,
            detail="Job already has auto_generate=true",
        )

    if job.status != "completed":
        raise HTTPException(
            status_code=409,
            detail="Job not in completed state",
        )

    # Count included pages
    included_count = (
        db.query(Page).filter(Page.job_id == job_id, Page.included.is_(True)).count()
    )

    # Update status synchronously so frontend polling sees the transition
    job.status = "summarizing"
    job.progress_percent = 50
    job.progress_message = "Starting generation..."
    db.commit()

    # Enqueue continue_generation task
    enqueue_job("continue_generation", str(job.id))

    return GenerateResponse(
        status="queued",
        message=f"Generation started for {included_count} pages",
    )


# Map file_type keys to download filenames
FILE_TYPE_TO_FILENAME = {
    "llms_txt": "llms.txt",
    "llms_ctx": "llms-ctx.txt",
}


@app.get("/api/jobs/{job_id}/download/{file_type}")
def download_file(job_id: UUID, file_type: str, db: Session = Depends(get_db)):
    """Download a specific generated file variant."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.result_files or file_type not in job.result_files:
        raise HTTPException(status_code=404, detail=f"File type '{file_type}' not found")

    storage = get_storage()
    content = storage.read(job.result_files[file_type])
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")

    filename = FILE_TYPE_TO_FILENAME.get(file_type, f"{file_type}.txt")

    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/jobs/{job_id}/download")
def download_result(job_id: UUID, db: Session = Depends(get_db)):
    """Download the generated llms.txt file (backward-compatible endpoint)."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.result_files or "llms_txt" not in job.result_files:
        raise HTTPException(status_code=404, detail="File not ready")

    storage = get_storage()
    content = storage.read(job.result_files["llms_txt"])
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")

    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="llms.txt"'},
    )
