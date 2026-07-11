from dataclasses import dataclass
import logging

from sqlalchemy.orm import Session

from app.core.time_utils import to_naive_utc, utc_now
from app.db.models import Issue, Source
from app.repositories.issue_repo import due_metric_issues, mark_issue_deleted, update_issue_from_detail
from app.repositories.job_repo import add_log, create_job, finish_job
from app.services.github_client import GitHubClient, GitHubNotFoundError, GitHubRateLimitError
from app.services.scheduler_service import source_log_name


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MetricTarget:
    issue_id: int
    source_id: int | None
    repo_full_name: str
    issue_number: int
    tracking_until_expired: bool


class MetricService:
    def __init__(self, github_client: GitHubClient | None = None):
        self.github_client = github_client or GitHubClient()

    def run_due_metrics(self, db: Session, limit: int = 100):
        now = utc_now()
        targets = [
            MetricTarget(
                issue.id,
                issue.source_id,
                issue.repo_full_name,
                issue.issue_number,
                bool(issue.tracking_until and issue.tracking_until <= to_naive_utc(now)),
            )
            for issue in due_metric_issues(db, now, limit)
        ]

        jobs = []
        grouped_targets: dict[int | None, list[MetricTarget]] = {}
        for target in targets:
            grouped_targets.setdefault(target.source_id, []).append(target)

        for source_id, source_targets in grouped_targets.items():
            job, hit_rate_limit = self._run_target_group(db, source_id, source_targets, now)
            jobs.append(job)
            if hit_rate_limit:
                break

        return jobs

    def _run_target_group(
        self,
        db: Session,
        source_id: int | None,
        targets: list[MetricTarget],
        now,
    ):
        source_name = self._source_name(db, source_id, targets)
        expired_count = sum(1 for target in targets if target.tracking_until_expired)
        logger.info(
            "Bat dau cap nhat metrics | source=%s id=%s posts=%s skipped_old=%s",
            source_name,
            source_id or 0,
            len(targets),
            expired_count,
        )

        job = create_job(db, "update_metrics", source_id, now)
        db.commit()
        db.refresh(job)

        hit_rate_limit = False
        job.issues_found = len(targets)
        job.issues_updated = len(targets)
        for target in targets:
            try:
                issue_data = self.github_client.get_issue_detail(
                    target.repo_full_name,
                    target.issue_number,
                )
                issue = db.get(Issue, target.issue_id)
                if issue is None:
                    job.items_failed += 1
                    self._record_job_error(job, f"Issue {target.issue_id} not found")
                    continue
                update_issue_from_detail(db, issue, issue_data, job.id, utc_now())
                db.commit()
            except GitHubNotFoundError as exc:
                job.items_failed += 1
                self._record_job_error(job, str(exc))
                issue = db.get(Issue, target.issue_id)
                if issue is not None:
                    mark_issue_deleted(db, issue)
                add_log(
                    db,
                    str(exc),
                    log_level="WARNING",
                    job_id=job.id,
                    error_type=type(exc).__name__,
                )
                db.commit()
            except GitHubRateLimitError as exc:
                job.items_failed += 1
                self._record_job_error(job, str(exc))
                add_log(
                    db,
                    str(exc),
                    log_level="WARNING",
                    job_id=job.id,
                    error_type=type(exc).__name__,
                )
                db.commit()
                hit_rate_limit = True
                break
            except Exception as exc:
                job.items_failed += 1
                self._record_job_error(job, str(exc))
                add_log(db, str(exc), job_id=job.id, error_type=type(exc).__name__)
                db.commit()

        finish_job(db, job, "done", utc_now(), job.error_message)
        job.posts_expired = expired_count
        db.commit()
        db.refresh(job)
        job.posts_expired = expired_count
        logger.info(
            "Hoan tat cap nhat metrics | source=%s id=%s updated=%s failed=%s",
            source_name,
            source_id or 0,
            job.issues_updated,
            job.items_failed,
        )
        return job, hit_rate_limit

    @staticmethod
    def _record_job_error(job, message: str) -> None:
        if job.error_message:
            job.error_message = f"{job.error_message}\n{message}"
        else:
            job.error_message = message

    @staticmethod
    def _source_name(db: Session, source_id: int | None, targets: list[MetricTarget]) -> str:
        if source_id is not None:
            source = db.get(Source, source_id)
            if source is not None:
                return source_log_name(source.display_name or source.identifier)
        if targets:
            return source_log_name(targets[0].repo_full_name)
        return "unknown"
