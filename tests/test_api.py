"""API tests for critical paths only."""

from fastapi.testclient import TestClient
from starlette import status

from app.jobs.models import Job, Page
from app.jobs.schemas import JobStatus


def test_health_check(client: TestClient):
    """Health endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "healthy"


def test_create_job(client: TestClient):
    """POST /api/jobs creates a job and returns 201."""
    response = client.post("/api/jobs", json={"url": "https://example.com"})
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert "id" in data
    assert data["url"] == "https://example.com/"
    assert data["status"] == "pending"


def test_get_existing_job(client: TestClient, db):
    """GET /api/jobs/{id} returns job details."""
    job = Job(url="https://example.com")
    db.add(job)
    db.commit()
    db.refresh(job)

    response = client.get(f"/api/jobs/{job.id}")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == str(job.id)


def test_update_pages(client: TestClient, db):
    """PATCH /api/jobs/{id}/pages updates page inclusion."""
    job = Job(url="https://example.com")
    db.add(job)
    db.commit()
    db.refresh(job)

    page = Page(job_id=job.id, url="https://example.com/page1", included=True)
    db.add(page)
    db.commit()
    db.refresh(page)

    response = client.patch(
        f"/api/jobs/{job.id}/pages",
        json={"page_ids": [str(page.id)], "included": False},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["updated"] == 1


def test_download_file(client: TestClient, db, mock_storage):
    """GET /api/jobs/{id}/download/{type} returns file content."""
    result_files = {
        "llms_txt": "job-123/llms.txt",
        "llms_ctx": "job-123/llms-ctx.txt",
    }
    job = Job(
        url="https://example.com",
        status=JobStatus.COMPLETED,
        result_files=result_files,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    mock_storage.read.return_value = "# Example Site\n> A test site"

    response = client.get(f"/api/jobs/{job.id}/download/llms_txt")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-disposition"] == 'attachment; filename="llms.txt"'
