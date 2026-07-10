from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("source_type", "identifier"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    identifier: Mapped[str] = mapped_column(String(300), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_accessible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_comments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_scraped: Mapped[datetime | None] = mapped_column(DateTime)
    next_scrape: Mapped[datetime | None] = mapped_column(DateTime)
    schedule_tier: Mapped[int | None] = mapped_column(Integer)
    schedule_override_minutes: Mapped[int | None] = mapped_column(Integer)


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("github_issue_id"),
        UniqueConstraint("repo_full_name", "issue_number"),
        CheckConstraint("state IN ('open', 'closed')"),
        CheckConstraint("metric_tier IN ('hot', 'high', 'medium', 'low', 'very_low', 'bootstrap')"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    github_issue_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"),
        index=True,
    )
    repo_full_name: Mapped[str] = mapped_column(String(300), nullable=False)
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    author_login: Mapped[str | None] = mapped_column(String(100))
    labels_json: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    comments_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    html_url: Mapped[str] = mapped_column(Text, nullable=False)
    issue_created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    issue_updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    is_tracked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tracking_until: Mapped[datetime | None] = mapped_column(DateTime)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_metric_update: Mapped[datetime | None] = mapped_column(DateTime)
    next_metric_update: Mapped[datetime | None] = mapped_column(DateTime)
    metric_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="bootstrap")

    metrics: Mapped[list["IssueMetric"]] = relationship(back_populates="issue")


class SourceIssue(Base):
    __tablename__ = "source_issues"

    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class AnalyticsCache(Base):
    __tablename__ = "analytics_cache"
    __table_args__ = (UniqueConstraint("source_id", "cache_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    cache_date: Mapped[date] = mapped_column(Date, nullable=False)
    issues_24h: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments_24h: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_tier: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class PipelineJob(Base):
    __tablename__ = "pipeline_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(30), nullable=False, default="scrape_issues")
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    issues_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    issues_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class IssueMetric(Base):
    __tablename__ = "issue_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    comments_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_jobs.id", ondelete="SET NULL"))

    issue: Mapped[Issue] = relationship(back_populates="metrics")


class IssueComment(Base):
    __tablename__ = "issue_comments"
    __table_args__ = (UniqueConstraint("github_comment_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    github_comment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    author_login: Mapped[str | None] = mapped_column(String(100))
    comment_body: Mapped[str | None] = mapped_column(Text)
    html_url: Mapped[str | None] = mapped_column(Text)
    comment_created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    comment_updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class PipelineLog(Base):
    __tablename__ = "pipeline_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_jobs.id", ondelete="SET NULL"))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    log_level: Mapped[str] = mapped_column(String(20), nullable=False, default="ERROR")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(100))
    error_details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
