from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.time_utils import utc_now
from app.db.models import Issue
from app.repositories.issue_repo import due_metric_issues, mark_issue_deleted, update_issue_from_detail
from app.repositories.job_repo import add_log, create_job, finish_job
from app.services.github_client import GitHubClient, GitHubNotFoundError


@dataclass(frozen=True)
class MetricTarget:
    issue_id: int
    repo_full_name: str
    issue_number: int


class MetricService:
    def __init__(self, github_client: GitHubClient | None = None):
        self.github_client = github_client or GitHubClient()

    def run_due_metrics(self, db: Session, limit: int = 100):
        now = utc_now()
        job = create_job(db, "update_metrics", None, now)
        targets = [
            MetricTarget(issue.id, issue.repo_full_name, issue.issue_number)
            for issue in due_metric_issues(db, now, limit)
        ]
        db.commit()
        db.refresh(job)

        job.issues_found = len(targets)
        for target in targets:
            try:
                issue_data = self.github_client.get_issue_detail(
                    target.repo_full_name,
                    target.issue_number,
                )
                issue = db.get(Issue, target.issue_id)
                if issue is None:
                    job.items_failed += 1
                    continue
                update_issue_from_detail(db, issue, issue_data, job.id, utc_now())
                db.commit()
            except GitHubNotFoundError as exc:
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
            except Exception as exc:
                job.items_failed += 1
                add_log(db, str(exc), job_id=job.id, error_type=type(exc).__name__)
                db.commit()

        finish_job(db, job, "done", utc_now())
        db.commit()
        db.refresh(job)
        return job
