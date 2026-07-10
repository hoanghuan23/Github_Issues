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
    def __init__(self, db_session):
        self.db_session = db_session
        self.comment_calls = 0

    def list_recent_repo_issues(self, source):
        assert not self.db_session.in_transaction()
        created_at = (utc_now() - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        return [make_issue(101, created_at, comments=2)]

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
    assert source.schedule_tier == 2
    assert job.status == "done"
    assert job.issues_found == 1
    assert job.issues_new == 1
    assert fake_client.comment_calls == 0

    issue = db_session.query(Issue).one()
    assert issue.source_id == source.id

    cache = db_session.query(AnalyticsCache).one()
    assert cache.source_id == source.id
    assert cache.total_issues == 1
    assert cache.total_comments == 2
    assert cache.growth_rate == 8


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
