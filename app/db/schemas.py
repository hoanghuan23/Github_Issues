from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SourceCreate(BaseModel):
    url: str
    include_comments: bool = False


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    identifier: str
    display_name: str | None = None
    include_comments: bool
    is_active: bool
    is_accessible: bool
    last_scraped: datetime | None = None
    next_scrape: datetime | None = None
    schedule_tier: int | None = None


class IssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    github_issue_id: int
    repo_full_name: str
    issue_number: int
    title: str
    author_login: str | None = None
    state: str
    comments_count: int
    html_url: str
    issue_created_at: datetime
    issue_updated_at: datetime
    is_tracked: bool
    is_deleted: bool
    metric_tier: str
    next_metric_update: datetime | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: str
    source_id: int | None = None
    status: str
    issues_found: int
    issues_new: int
    comments_found: int
    comments_new: int
    items_failed: int
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class SourceCreateResponse(BaseModel):
    source: SourceRead
    job: JobRead


class IssueListResponse(BaseModel):
    items: list[IssueRead]
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)

