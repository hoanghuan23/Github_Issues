from datetime import datetime, timedelta

from app.constants import (
    COMMENT_TIER_THRESHOLDS,
    ISSUE_METRIC_INTERVAL_MINUTES,
    SOURCE_INTERVAL_MINUTES,
    SOURCE_TIER_THRESHOLDS,
)
from app.core.time_utils import ensure_aware_utc


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

