from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.time_utils import utc_now
from app.db.models import AnalyticsCache, Issue
from app.db.database import get_db
from app.main import app
from app.repositories.issue_repo import upsert_analytics_cache
from app.services.source_service import SourceService


def make_issue(issue_id: int, created_at: str, comments: int = 0) -> dict:
    return {
        "github_issue_id": issue_id,
        "repo_full_name": "acme/repo",
        "issue_number": issue_id,
        "title": f"Issue {issue_id}",
        "author_login": "octocat",
        "state": "open",
        "comments_count": comments,
        "html_url": f"https://github.com/acme/repo/issues/{issue_id}",
        "issue_created_at": created_at,
        "issue_updated_at": created_at,
    }


class FakeGitHubClient:
    def __init__(self, db_session, issues=None):
        self.db_session = db_session
        self.comment_calls = 0
        self.issues = issues
        self.stop_at_created_at_values = []

    def list_recent_repo_issues(self, source, stop_at_created_at=None):
        return self.list_recent_source_issues(source, stop_at_created_at)

    def list_recent_source_issues(self, source, stop_at_created_at=None):
        assert not self.db_session.in_transaction()
        self.stop_at_created_at_values.append(stop_at_created_at)
        created_at = (utc_now() - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        return self.issues or [make_issue(101, created_at, comments=2)]

    def list_issue_comments(self, repo_full_name, issue_number):
        self.comment_calls += 1
        return []


def test_source_service_does_not_hold_transaction_while_calling_github(db_session):
    fake_client = FakeGitHubClient(db_session)
    source, job = SourceService(fake_client).create_source_and_scrape(
        db_session,
        "https://github.com/acme/repo/issues",
        include_comments=False,
    )

    assert source.identifier == "acme/repo"
    assert source.source_type == "repo"
    assert source.schedule_tier == 2
    assert job.status == "done"
    assert job.job_type == "scrape_issues"
    assert job.issues_found == 1
    assert job.issues_new == 1
    assert fake_client.comment_calls == 0

    issue = db_session.query(Issue).one()
    assert issue.source_id == source.id

    cache = db_session.query(AnalyticsCache).one()
    assert cache.source_id == source.id
    assert cache.total_issues == 1
    assert cache.total_comments == 2
    assert cache.top_issue_id == issue.id
    assert cache.growth_rate == 8


def test_source_service_due_scrape_uses_scrape_new_issues_job_type(db_session):
    fake_client = FakeGitHubClient(db_session)
    source, _initial_job = SourceService(fake_client).create_source_and_scrape(
        db_session,
        "https://github.com/acme/repo/issues",
        include_comments=False,
    )

    _source, job = SourceService(fake_client).scrape_source(db_session, source.id)

    assert job.status == "done"
    assert job.job_type == "scrape_new_issues"
    assert fake_client.stop_at_created_at_values[0] is None
    assert fake_client.stop_at_created_at_values[1] is not None


def test_source_service_due_scrape_passes_latest_issue_created_at(db_session):
    old_created_at = (utc_now() - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    new_created_at = (utc_now() - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    fake_client = FakeGitHubClient(
        db_session,
        issues=[make_issue(301, old_created_at, comments=1)],
    )
    source, _initial_job = SourceService(fake_client).create_source_and_scrape(
        db_session,
        "https://github.com/acme/repo/issues",
        include_comments=False,
    )

    fake_client.issues = [make_issue(302, new_created_at, comments=2)]
    _source, _job = SourceService(fake_client).scrape_source(db_session, source.id)

    assert fake_client.stop_at_created_at_values[1] == db_session.query(Issue).filter_by(
        github_issue_id=301,
    ).one().issue_created_at


def test_analytics_cache_tracks_top_issue_by_comment_count(db_session):
    created_at = (utc_now() - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    fake_client = FakeGitHubClient(
        db_session,
        issues=[
            make_issue(201, created_at, comments=2),
            make_issue(202, created_at, comments=9),
            make_issue(203, created_at, comments=4),
        ],
    )
    source, _job = SourceService(fake_client).create_source_and_scrape(
        db_session,
        "https://github.com/acme/repo/issues",
        include_comments=False,
    )

    top_issue = db_session.query(Issue).filter_by(github_issue_id=202).one()
    cache = db_session.query(AnalyticsCache).one()
    assert cache.source_id == source.id
    assert cache.total_issues == 3
    assert cache.total_comments == 15
    assert cache.top_issue_id == top_issue.id


def test_analytics_cache_updates_same_day_and_inserts_next_day(db_session):
    fake_client = FakeGitHubClient(db_session)
    source, _job = SourceService(fake_client).create_source_and_scrape(
        db_session,
        "https://github.com/acme/repo/issues",
        include_comments=False,
    )

    first_cache = db_session.query(AnalyticsCache).one()
    upsert_analytics_cache(
        db_session,
        source.id,
        issues_24h=3,
        comments_24h=4,
        source_score=18,
        now=first_cache.cached_at,
    )
    db_session.commit()

    caches = db_session.query(AnalyticsCache).all()
    assert len(caches) == 1
    assert caches[0].total_issues == 3

    upsert_analytics_cache(
        db_session,
        source.id,
        issues_24h=5,
        comments_24h=6,
        source_score=28,
        now=first_cache.cached_at + timedelta(days=1),
    )
    db_session.commit()

    assert db_session.query(AnalyticsCache).count() == 2


def test_post_sources_endpoint_with_mocked_github(db_session, monkeypatch):
    fake_client = FakeGitHubClient(db_session)
    monkeypatch.setattr(
        "app.api.routes_sources.SourceService",
        lambda: SourceService(fake_client),
    )

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        response = client.post(
            "/sources",
            json={
                "url": "https://github.com/acme/repo/issues",
                "include_comments": False,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["source"]["identifier"] == "acme/repo"
    assert body["job"]["issues_new"] == 1


def test_source_service_creates_organization_source(db_session):
    fake_client = FakeGitHubClient(db_session)
    source, job = SourceService(fake_client).create_source_and_scrape(
        db_session,
        "https://github.com/search?q=org:kubernetes is:issue state:open&type=issues",
        include_comments=False,
    )

    assert source.source_type == "organization"
    assert source.identifier == "kubernetes"
    assert job.status == "done"


def test_source_service_creates_keyword_source(db_session):
    fake_client = FakeGitHubClient(db_session)
    source, job = SourceService(fake_client).create_source_and_scrape(
        db_session,
        'https://github.com/search?q="memory leak" is:issue state:open&type=issues',
        include_comments=False,
    )

    assert source.source_type == "keyword"
    assert source.identifier == "memory leak"
    assert job.status == "done"


def test_source_service_creates_label_source(db_session):
    fake_client = FakeGitHubClient(db_session)
    source, job = SourceService(fake_client).create_source_and_scrape(
        db_session,
        "https://github.com/microsoft/vscode/issues?q=is:issue state:open label:bug",
        include_comments=False,
    )

    assert source.source_type == "label"
    assert source.identifier == "microsoft/vscode:bug"
    assert job.status == "done"
