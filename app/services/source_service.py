from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.time_utils import to_naive_utc, utc_now
from app.db.models import PipelineJob
from app.repositories.comment_repo import upsert_comments
from app.repositories.issue_repo import (
    latest_source_issue_created_at,
    source_24h_counts,
    upsert_analytics_cache,
    upsert_issue_from_github,
)
from app.repositories.job_repo import add_log, create_job, finish_job
from app.repositories.source_repo import get_or_create_repo_source
from app.services.github_client import GitHubClient, parse_repo_issues_url
from app.services.scheduler_service import (
    calculate_source_next_scrape,
    calculate_source_score,
    calculate_source_tier,
)


@dataclass
class PendingCommentFetch:
    issue_id: int
    repo_full_name: str
    issue_number: int


class SourceService:
    def __init__(self, github_client: GitHubClient | None = None):
        self.github_client = github_client or GitHubClient()

    def create_source_and_scrape(
        self,
        db: Session,
        url: str,
        include_comments: bool,
    ):
        source_info = parse_repo_issues_url(url)
        now = utc_now()

        source, _created = get_or_create_repo_source(db, source_info.identifier, include_comments)
        job = create_job(db, "scrape_issues", source.id, now)
        db.commit()
        db.refresh(source)
        db.refresh(job)

        return self.scrape_source(db, source.id, job.id)

    def scrape_source(self, db: Session, source_id: int, job_id: int | None = None):
        from app.repositories.source_repo import get_source

        now = utc_now()
        source = get_source(db, source_id)
        if source is None:
            raise ValueError("source not found")
        source_identifier = source.identifier
        include_comments = source.include_comments
        schedule_override_minutes = source.schedule_override_minutes
        source_info = parse_repo_issues_url(
            f"https://github.com/{source_identifier}/issues"
        )

        if job_id is None:
            job = create_job(db, "scrape_new_issues", source.id, now)
            db.commit()
            db.refresh(job)
            job_id = job.id
        else:
            job = db.get(PipelineJob, job_id)
            if job is None:
                raise ValueError("job not found")

        db.commit()

        stop_at_created_at = (
            latest_source_issue_created_at(db, source_id)
            if job.job_type == "scrape_new_issues"
            else None
        )
        db.commit()

        try:
            issues = self.github_client.list_recent_repo_issues(
                source_info,
                stop_at_created_at=stop_at_created_at,
            )
        except Exception as exc:
            job = db.get(PipelineJob, job_id)
            if job:
                add_log(db, str(exc), job_id=job.id, source_id=source_id, error_type=type(exc).__name__)
                finish_job(db, job, "failed", utc_now(), str(exc))
                db.commit()
            raise

        pending_comments: list[PendingCommentFetch] = []
        now = utc_now()
        job = db.get(PipelineJob, job_id)
        if job is None:
            raise ValueError("job not found")
        source = get_source(db, source_id)
        if source is None:
            raise ValueError("source not found")

        job.issues_found = len(issues)
        for issue_data in issues:
            issue, is_new, comments_increased = upsert_issue_from_github(
                db,
                issue_data,
                source_id=source_id,
                job_id=job.id,
                now=now,
            )
            if is_new:
                job.issues_new += 1
            if include_comments and (is_new or comments_increased):
                pending_comments.append(
                    PendingCommentFetch(
                        issue_id=issue.id,
                        repo_full_name=issue.repo_full_name,
                        issue_number=issue.issue_number,
                    )
                )

        db.flush()
        issues_24h, comments_24h = source_24h_counts(db, source_id, now)
        score = calculate_source_score(issues_24h, comments_24h)
        tier = calculate_source_tier(score)
        upsert_analytics_cache(db, source_id, issues_24h, comments_24h, score, now)
        source.schedule_tier = tier
        source.last_scraped = to_naive_utc(now)
        source.next_scrape = to_naive_utc(calculate_source_next_scrape(tier, now, schedule_override_minutes))
        db.commit()

        for pending in pending_comments:
            try:
                comments = self.github_client.list_issue_comments(
                    pending.repo_full_name,
                    pending.issue_number,
                )
                upsert_comments(db, pending.issue_id, comments, utc_now())
                db.commit()
            except Exception as exc:
                job.items_failed += 1
                add_log(
                    db,
                    str(exc),
                    job_id=job.id,
                    source_id=source_id,
                    error_type=type(exc).__name__,
                )
                db.commit()

        finish_job(db, job, "done", utc_now())
        db.commit()
        db.refresh(source)
        db.refresh(job)
        return source, job
