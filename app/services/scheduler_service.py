from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.constants import (
    COMMENT_TIER_THRESHOLDS,
    ISSUE_METRIC_INTERVAL_MINUTES,
    SOURCE_INTERVAL_MINUTES,
    SOURCE_TIER_THRESHOLDS,
)
from app.core.time_utils import ensure_aware_utc, utc_now
from app.repositories.source_repo import due_sources

if TYPE_CHECKING:
    from app.services.metric_service import MetricService
    from app.services.source_service import SourceService


@dataclass(frozen=True)
class SchedulerRunResult:
    sources_attempted: int
    sources_failed: int
    metrics_job_ids: list[int]


def calculate_metric_tier(comments_count: int) -> str:
    for threshold, tier in COMMENT_TIER_THRESHOLDS:
        if comments_count >= threshold:
            return tier
    return "very_low"


def calculate_issue_metric_interval_minutes(
    metric_tier: str,
    issue_created_at: datetime,
    now: datetime,
) -> int | None:
    age_hours = (ensure_aware_utc(now) - ensure_aware_utc(issue_created_at)).total_seconds() / 3600
    for max_age_hours, minutes in ISSUE_METRIC_INTERVAL_MINUTES[metric_tier]:
        if age_hours <= max_age_hours:
            return minutes
    return None


def calculate_next_metric_update(
    metric_tier: str,
    issue_created_at: datetime,
    now: datetime,
) -> datetime | None:
    minutes = calculate_issue_metric_interval_minutes(metric_tier, issue_created_at, now)
    if minutes is None:
        return None
    return now + timedelta(minutes=minutes)


def calculate_source_score(issues_24h: int, comments_24h: int) -> int:
    return issues_24h * 2 + comments_24h * 3


def calculate_source_tier(source_score: int) -> int:
    for threshold, tier in SOURCE_TIER_THRESHOLDS:
        if source_score >= threshold:
            return tier
    return 1


def calculate_source_next_scrape(
    tier: int,
    now: datetime,
    override_minutes: int | None = None,
) -> datetime:
    minutes = override_minutes or SOURCE_INTERVAL_MINUTES[tier]
    return now + timedelta(minutes=minutes)


class SchedulerService:
    def __init__(
        self,
        source_service: "SourceService | None" = None,
        metric_service: "MetricService | None" = None,
    ):
        from app.services.metric_service import MetricService
        from app.services.source_service import SourceService

        self.source_service = source_service or SourceService()
        self.metric_service = metric_service or MetricService()

    def run_due(self, db: Session, batch_size: int = 50) -> SchedulerRunResult:
        now = utc_now()
        source_ids = [source.id for source in due_sources(db, now, batch_size)]
        sources_failed = 0

        for source_id in source_ids:
            try:
                self.source_service.scrape_source(db, source_id)
            except Exception:
                sources_failed += 1

        metrics_jobs = self.metric_service.run_due_metrics(db, batch_size)

        return SchedulerRunResult(
            sources_attempted=len(source_ids),
            sources_failed=sources_failed,
            metrics_job_ids=[job.id for job in metrics_jobs],
        )
