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


def add_due_issue(db_session):
    now = utc_now()
    issue = Issue(
        github_issue_id=1,
        repo_full_name="acme/repo",
        issue_number=1,
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


def test_run_due_metrics_marks_404_issue_deleted(db_session):
    issue_id = add_due_issue(db_session)

    MetricService(NotFoundGitHubClient()).run_due_metrics(db_session)

    issue = db_session.get(Issue, issue_id)
    assert issue.is_deleted is True
    assert issue.is_tracked is False
    assert issue.next_metric_update is None


def test_run_due_metrics_stops_tracking_closed_issue(db_session):
    issue_id = add_due_issue(db_session)

    MetricService(ClosedIssueGitHubClient()).run_due_metrics(db_session)

    issue = db_session.get(Issue, issue_id)
    assert issue.state == "closed"
    assert issue.comments_count == 9
    assert issue.is_tracked is False
    assert issue.next_metric_update is None

