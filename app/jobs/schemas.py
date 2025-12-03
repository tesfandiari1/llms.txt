from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, HttpUrl


class JobStatus(str, Enum):
    PENDING = "pending"
    DISCOVERING = "discovering"
    CATEGORIZING = "categorizing"
    EXTRACTING = "extracting"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobCreate(BaseModel):
    url: HttpUrl
    mode: str = "auto"
    max_pages: int = 100
    auto_generate: bool = True


class JobResponse(BaseModel):
    id: UUID
    url: str
    status: JobStatus
    mode: str
    auto_generate: bool
    progress_percent: int
    progress_message: str | None
    pages_total: int | None
    pages_processed: int
    site_title: str | None
    site_summary: str | None
    result_files: dict | None
    error_message: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PageResponse(BaseModel):
    id: UUID
    url: str
    title: str | None
    category: str | None
    importance_score: int
    has_markdown: bool
    has_summary: bool
    included: bool

    model_config = ConfigDict(from_attributes=True)


class PageListResponse(BaseModel):
    pages: list[PageResponse]
    total: int
    included_count: int


class PageUpdateRequest(BaseModel):
    page_ids: list[UUID]
    included: bool


class PageUpdateResponse(BaseModel):
    updated: int


class GenerateResponse(BaseModel):
    status: str
    message: str

