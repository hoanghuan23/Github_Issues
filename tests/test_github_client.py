from datetime import timedelta

import pytest

from app.core.time_utils import utc_now
from app.services.github_client import GitHubClient, GitHubRateLimitError, map_issue_item, parse_repo_issues_url


def issue_item(issue_id: int, created_at: str, pull_request: bool = False) -> dict:
    item = {
        "id": issue_id,
        "number": issue_id,
        "title": f"Issue {issue_id}",
        "user": {"login": "octocat"},
        "state": "open",
        "comments": issue_id % 3,
        "html_url": f"https://github.com/acme/repo/issues/{issue_id}",
        "created_at": created_at,
        "updated_at": created_at,
    }
    if pull_request:
        item["pull_request"] = {}
    return item


class FakeResponse:
    def __init__(self, payload, status_code: int = 200, headers=None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, headers, params=None, timeout=30):
        self.calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        return FakeResponse(self.pages[len(self.calls) - 1])


def test_parse_repo_issues_url():
    source = parse_repo_issues_url("https://github.com/microsoft/vscode/issues")
    assert source.owner == "microsoft"
    assert source.repo == "vscode"
    assert source.identifier == "microsoft/vscode"


def test_parse_repo_issues_url_rejects_invalid_url():
    with pytest.raises(ValueError):
        parse_repo_issues_url("https://api.github.com/repos/microsoft/vscode/issues")


def test_map_issue_item_skips_pull_request():
    assert map_issue_item(issue_item(1, "2026-01-01T00:00:00Z", pull_request=True), "acme/repo") is None


def test_list_recent_repo_issues_skips_pr_and_stops_at_older_issue():
    now = utc_now()
    recent = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    old = (now - timedelta(hours=25)).isoformat().replace("+00:00", "Z")
    session = FakeSession([[issue_item(1, recent), issue_item(2, recent, True), issue_item(3, old)]])
    client = GitHubClient(token="token", session=session)

    issues = client.list_recent_repo_issues(parse_repo_issues_url("https://github.com/acme/repo/issues"))

    assert [issue["github_issue_id"] for issue in issues] == [1]
    assert session.calls[0]["params"]["sort"] == "created"


def test_list_recent_repo_issues_stops_at_latest_saved_created_at():
    now = utc_now()
    latest_saved_dt = now - timedelta(hours=1)
    newest = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    latest_saved = latest_saved_dt.isoformat().replace("+00:00", "Z")
    older = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    session = FakeSession(
        [
            [issue_item(1, newest), issue_item(2, latest_saved)],
            [issue_item(3, older)],
        ]
    )
    client = GitHubClient(token="token", session=session)

    issues = client.list_recent_repo_issues(
        parse_repo_issues_url("https://github.com/acme/repo/issues"),
        stop_at_created_at=latest_saved_dt,
    )

    assert [issue["github_issue_id"] for issue in issues] == [1]
    assert len(session.calls) == 1


def test_get_issue_detail_raises_rate_limit_error():
    session = FakeSession([])
    session.get = lambda url, headers, params=None, timeout=30: FakeResponse(
        {"message": "API rate limit exceeded"},
        status_code=403,
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1760000000"},
    )
    client = GitHubClient(token="token", session=session)

    with pytest.raises(GitHubRateLimitError, match="GitHub rate limit exceeded"):
        client.get_issue_detail("acme/repo", 1)
