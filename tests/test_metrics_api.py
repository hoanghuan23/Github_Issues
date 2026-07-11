from datetime import timedelta

from app.core.time_utils import to_naive_utc, utc_now
from app.db.models import Issue
from app.services.metric_service import MetricService


class NotFoundGitHubClient:
    def get_issue_detail(self, repo_full_name: str, issue_number: int):
        from app.services.github_client import GitHubNotFoundError

        raise GitHubNotFoundError("not found")


class ClosedIssueGitHubClient:
    def get_issue_detail(self, repo_full_name: str, issue_number: int):
        now = utc_now().isoformat().replace("+00:00", "Z")
        return {
            "github_issue_id": 1,
            "repo_full_name": repo_full_name,
            "issue_number": issue_number,
            "title": "Closed issue",
            "author_login": "octocat",
            "state": "closed",
            "comments_count": 9,
            "html_url": "https://github.com/acme/repo/issues/1",
            "issue_created_at": now,
            "issue_updated_at": now,
        }


class FailingGitHubClient:
    def get_issue_detail(self, repo_full_name: str, issue_number: int):
        raise RuntimeError(f"failed to update {repo_full_name}#{issue_number}")


def add_due_issue(db_session, issue_number: int = 1):
    now = utc_now()
    issue = Issue(
        github_issue_id=issue_number,
        repo_full_name="acme/repo",
        issue_number=issue_number,
        title="Open issue",
        state="open",
        comments_count=0,
        html_url="https://github.com/acme/repo/issues/1",
        issue_created_at=to_naive_utc(now - timedelta(hours=1)),
        issue_updated_at=to_naive_utc(now - timedelta(hours=1)),
        is_tracked=True,
        tracking_until=to_naive_utc(now + timedelta(hours=23)),
        next_metric_update=to_naive_utc(now - timedelta(minutes=1)),
    )
    db_session.add(issue)
    db_session.commit()
    return issue.id


def add_due_issues(db_session, count: int):
    return [add_due_issue(db_session, issue_number) for issue_number in range(1, count + 1)]


def test_run_due_metrics_marks_404_issue_deleted(db_session):
    issue_id = add_due_issue(db_session)

    job = MetricService(NotFoundGitHubClient()).run_due_metrics(db_session)

    issue = db_session.get(Issue, issue_id)
    assert issue.is_deleted is True
    assert issue.is_tracked is False
    assert issue.next_metric_update is None
    assert job.issues_updated == 1
    assert job.items_failed == 1
    assert job.error_message == "not found"


def test_run_due_metrics_stops_tracking_closed_issue(db_session):
    issue_id = add_due_issue(db_session)

    MetricService(ClosedIssueGitHubClient()).run_due_metrics(db_session)

    issue = db_session.get(Issue, issue_id)
    assert issue.state == "closed"
    assert issue.comments_count == 9
    assert issue.is_tracked is False
    assert issue.next_metric_update is None


def test_run_due_metrics_counts_due_targets_as_updated(db_session):
    add_due_issues(db_session, 5)

    job = MetricService(ClosedIssueGitHubClient()).run_due_metrics(db_session)

    assert job.issues_found == 5
    assert job.issues_updated == 5
    assert job.items_failed == 0
    assert job.error_message is None


def test_run_due_metrics_records_update_failures_on_job(db_session):
    add_due_issue(db_session)

    job = MetricService(FailingGitHubClient()).run_due_metrics(db_session)

    assert job.issues_updated == 1
    assert job.items_failed == 1
    assert job.error_message == "failed to update acme/repo#1"
