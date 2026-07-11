from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time_utils import parse_github_datetime, to_naive_utc
from app.db.models import AnalyticsCache, Issue, IssueMetric, SourceIssue
from app.services.scheduler_service import calculate_metric_tier, calculate_next_metric_update


def upsert_issue_from_github(
    db: Session,
    issue_data: dict,
    source_id: int,
    job_id: int | None,
    now: datetime,
) -> tuple[Issue, bool, bool]:
    existing = db.scalar(
        select(Issue).where(Issue.github_issue_id == issue_data["github_issue_id"])
    )
    is_new = existing is None
    old_comments_count = existing.comments_count if existing else None

    issue_created_at = to_naive_utc(parse_github_datetime(issue_data["issue_created_at"]))
    issue_updated_at = to_naive_utc(parse_github_datetime(issue_data["issue_updated_at"]))
    now_naive = to_naive_utc(now)
    tracking_until = issue_created_at + timedelta(hours=24)
    metric_tier = calculate_metric_tier(issue_data["comments_count"])
    is_tracked = now_naive < tracking_until and issue_data["state"] == "open"
    next_metric_update = (
        to_naive_utc(calculate_next_metric_update(metric_tier, issue_created_at, now))
        if is_tracked
        else None
    )

    if existing is None:
        issue = Issue(
            github_issue_id=issue_data["github_issue_id"],
            source_id=source_id,
            repo_full_name=issue_data["repo_full_name"],
            issue_number=issue_data["issue_number"],
            title=issue_data["title"],
            author_login=issue_data["author_login"],
            state=issue_data["state"],
            comments_count=issue_data["comments_count"],
            html_url=issue_data["html_url"],
            issue_created_at=issue_created_at,
            issue_updated_at=issue_updated_at,
        )
        db.add(issue)
    else:
        issue = existing
        issue.source_id = source_id
        issue.title = issue_data["title"]
        issue.author_login = issue_data["author_login"]
        issue.state = issue_data["state"]
        issue.comments_count = issue_data["comments_count"]
        issue.html_url = issue_data["html_url"]
        issue.issue_updated_at = issue_updated_at
        issue.is_deleted = False

    issue.metric_tier = metric_tier
    issue.tracking_until = tracking_until
    issue.is_tracked = is_tracked
    issue.last_metric_update = now_naive
    issue.next_metric_update = next_metric_update
    db.flush()

    link = db.get(SourceIssue, {"source_id": source_id, "issue_id": issue.id})
    if link:
        link.last_seen_at = now_naive
    else:
        db.add(SourceIssue(source_id=source_id, issue_id=issue.id, last_seen_at=now_naive))

    db.add(IssueMetric(issue_id=issue.id, comments_count=issue.comments_count, job_id=job_id, recorded_at=now_naive))
    comments_increased = old_comments_count is not None and issue.comments_count > old_comments_count
    return issue, is_new, comments_increased


def source_24h_counts(db: Session, source_id: int, now: datetime) -> tuple[int, int]:
    cutoff = to_naive_utc(now - timedelta(hours=24))
    row = db.execute(
        select(func.count(Issue.id), func.coalesce(func.sum(Issue.comments_count), 0))
        .join(SourceIssue, SourceIssue.issue_id == Issue.id)
        .where(SourceIssue.source_id == source_id, Issue.issue_created_at >= cutoff)
    ).one()
    return int(row[0]), int(row[1])


def latest_source_issue_created_at(db: Session, source_id: int) -> datetime | None:
    return db.scalar(
        select(func.max(Issue.issue_created_at))
        .join(SourceIssue, SourceIssue.issue_id == Issue.id)
        .where(SourceIssue.source_id == source_id)
    )


def upsert_analytics_cache(
    db: Session,
    source_id: int,
    issues_24h: int,
    comments_24h: int,
    source_score: int,
    now: datetime,
) -> AnalyticsCache:
    now_naive = to_naive_utc(now)
    cache_date = now_naive.date()
    cache = db.scalar(
        select(AnalyticsCache).where(
            AnalyticsCache.source_id == source_id,
            AnalyticsCache.date == cache_date,
        )
    )
    if cache is None:
        cache = AnalyticsCache(source_id=source_id, date=cache_date)
        db.add(cache)

    cutoff = to_naive_utc(now - timedelta(hours=24))
    top_issue_id = db.scalar(
        select(Issue.id)
        .join(SourceIssue, SourceIssue.issue_id == Issue.id)
        .where(SourceIssue.source_id == source_id, Issue.issue_created_at >= cutoff)
        .order_by(Issue.comments_count.desc(), Issue.id.asc())
        .limit(1)
    )

    cache.total_issues = issues_24h
    cache.total_comments = comments_24h
    cache.avg_comments_per_issue = comments_24h / issues_24h if issues_24h else 0.0
    cache.top_issue_id = top_issue_id
    cache.growth_rate = float(source_score)
    cache.cached_at = now_naive
    return cache


def list_issues(
    db: Session,
    repo_full_name: str | None = None,
    source_id: int | None = None,
    metric_tier: str | None = None,
    is_tracked: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Issue]:
    stmt = select(Issue).order_by(Issue.issue_created_at.desc()).limit(limit).offset(offset)
    if repo_full_name:
        stmt = stmt.where(Issue.repo_full_name == repo_full_name)
    if source_id is not None:
        stmt = stmt.where(Issue.source_id == source_id)
    if metric_tier:
        stmt = stmt.where(Issue.metric_tier == metric_tier)
    if is_tracked is not None:
        stmt = stmt.where(Issue.is_tracked == is_tracked)
    return list(db.scalars(stmt))


def due_metric_issues(db: Session, now: datetime, limit: int = 100) -> list[Issue]:
    return list(
        db.scalars(
            select(Issue)
            .where(Issue.is_tracked == True, Issue.next_metric_update <= to_naive_utc(now))  # noqa: E712
            .order_by(Issue.next_metric_update.asc())
            .limit(limit)
        )
    )


def update_issue_from_detail(
    db: Session,
    issue: Issue,
    issue_data: dict,
    job_id: int | None,
    now: datetime,
) -> Issue:
    issue_updated_at = to_naive_utc(parse_github_datetime(issue_data["issue_updated_at"]))
    now_naive = to_naive_utc(now)
    metric_tier = calculate_metric_tier(issue_data["comments_count"])

    issue.title = issue_data["title"]
    issue.author_login = issue_data["author_login"]
    issue.state = issue_data["state"]
    issue.comments_count = issue_data["comments_count"]
    issue.html_url = issue_data["html_url"]
    issue.issue_updated_at = issue_updated_at
    issue.metric_tier = metric_tier
    issue.last_metric_update = now_naive
    issue.is_deleted = False

    if issue.state != "open" or (issue.tracking_until and now_naive >= issue.tracking_until):
        issue.is_tracked = False
        issue.next_metric_update = None
    else:
        issue.is_tracked = True
        issue.next_metric_update = to_naive_utc(
            calculate_next_metric_update(metric_tier, issue.issue_created_at, now)
        )

    db.add(IssueMetric(issue_id=issue.id, comments_count=issue.comments_count, job_id=job_id, recorded_at=now_naive))
    return issue


def mark_issue_deleted(db: Session, issue: Issue) -> Issue:
    issue.is_deleted = True
    issue.is_tracked = False
    issue.next_metric_update = None
    return issue
