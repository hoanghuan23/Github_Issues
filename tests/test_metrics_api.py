import logging
from datetime import timedelta

from app.core.time_utils import to_naive_utc, utc_now
from app.db.models import Issue, Source
from app.services.github_client import GitHubRateLimitError
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


class RateLimitedGitHubClient:
    def __init__(self):
        self.calls = 0

    def get_issue_detail(self, repo_full_name: str, issue_number: int):
        self.calls += 1
        raise GitHubRateLimitError(f"GitHub rate limit exceeded for {repo_full_name}#{issue_number}")


def add_source(db_session, identifier: str = "acme/repo"):
    source = Source(
        source_type="repo",
        identifier=identifier,
        display_name=identifier,
    )
    db_session.add(source)
    db_session.commit()
    return source


def add_due_issue(db_session, issue_number: int = 1, source_id: int | None = None):
    now = utc_now()
    issue = Issue(
        github_issue_id=issue_number,
        source_id=source_id,
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

    job = MetricService(NotFoundGitHubClient()).run_due_metrics(db_session)[0]

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

    job = MetricService(ClosedIssueGitHubClient()).run_due_metrics(db_session)[0]

    assert job.issues_found == 5
    assert job.issues_updated == 5
    assert job.items_failed == 0
    assert job.error_message is None


def test_run_due_metrics_records_update_failures_on_job(db_session):
    add_due_issue(db_session)

    job = MetricService(FailingGitHubClient()).run_due_metrics(db_session)[0]

    assert job.issues_updated == 1
    assert job.items_failed == 1
    assert job.error_message == "failed to update acme/repo#1"


def test_run_due_metrics_stops_batch_on_rate_limit(db_session):
    add_due_issues(db_session, 5)
    client = RateLimitedGitHubClient()

    job = MetricService(client).run_due_metrics(db_session)[0]

    assert client.calls == 1
    assert job.issues_found == 5
    assert job.items_failed == 1
    assert job.error_message == "GitHub rate limit exceeded for acme/repo#1"


def test_run_due_metrics_groups_jobs_by_source(db_session):
    source_one = add_source(db_session, "acme/one")
    source_two = add_source(db_session, "acme/two")
    add_due_issue(db_session, 1, source_one.id)
    add_due_issue(db_session, 2, source_two.id)
    add_due_issue(db_session, 3, source_one.id)

    jobs = MetricService(ClosedIssueGitHubClient()).run_due_metrics(db_session)

    assert [job.source_id for job in jobs] == [source_one.id, source_two.id]
    assert [job.issues_found for job in jobs] == [2, 1]


def test_run_due_metrics_logs_source_progress(db_session, caplog):
    source = add_source(db_session, "acme/repo")
    add_due_issue(db_session, 1, source.id)

    caplog.set_level(logging.INFO, logger="app.services.metric_service")
    MetricService(ClosedIssueGitHubClient()).run_due_metrics(db_session)

    assert f"Bat dau cap nhat metrics | source=repo id={source.id} posts=1 skipped_old=0" in caplog.messages
    assert f"Hoan tat cap nhat metrics | source=repo id={source.id} updated=1 failed=0" in caplog.messages
