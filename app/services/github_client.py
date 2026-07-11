from dataclasses import dataclass
from datetime import datetime, timezone
from datetime import timedelta
from urllib.parse import urlparse

import requests

from app.core.config import get_settings
from app.core.time_utils import parse_github_datetime, utc_now


GITHUB_API_URL = "https://api.github.com"


class GitHubNotFoundError(Exception):
    pass


class GitHubRateLimitError(Exception):
    pass


@dataclass(frozen=True)
class RepoIssuesSource:
    owner: str
    repo: str

    @property
    def identifier(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def api_path(self) -> str:
        return f"repos/{self.owner}/{self.repo}/issues"


def parse_repo_issues_url(url: str) -> RepoIssuesSource:
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip("/").split("/")
    if (
        parsed_url.scheme != "https"
        or parsed_url.netloc != "github.com"
        or len(path_parts) != 3
        or path_parts[2] != "issues"
    ):
        raise ValueError(
            "url must be https://github.com/{owner}/{repo}/issues"
        )
    return RepoIssuesSource(owner=path_parts[0], repo=path_parts[1])


class GitHubClient:
    def __init__(self, token: str | None = None, session: requests.Session | None = None):
        self.token = token if token is not None else get_settings().github_token
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def list_recent_repo_issues(
        self,
        source: RepoIssuesSource,
        max_hours_old: int = 24,
    ) -> list[dict]:
        url = f"{GITHUB_API_URL}/{source.api_path}"
        params = {
            "state": "open",
            "sort": "created",
            "direction": "desc",
            "per_page": 100,
            "page": 1,
        }
        cutoff = utc_now() - timedelta(hours=max_hours_old)
        results: list[dict] = []

        while True:
            response = self.session.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            items = response.json()
            if not items:
                break

            reached_old_issue = False
            for item in items:
                mapped = map_issue_item(item, source.identifier)
                if mapped is None:
                    continue
                if parse_github_datetime(mapped["issue_created_at"]) < cutoff:
                    reached_old_issue = True
                    break
                results.append(mapped)

            if reached_old_issue or len(items) < params["per_page"]:
                break
            params["page"] += 1

        return results

    def get_issue_detail(self, repo_full_name: str, issue_number: int) -> dict:
        url = f"{GITHUB_API_URL}/repos/{repo_full_name}/issues/{issue_number}"
        response = self.session.get(url, headers=self._headers(), timeout=30)
        if response.status_code == 404:
            raise GitHubNotFoundError(f"Issue not found: {repo_full_name}#{issue_number}")
        if response.status_code == 403 and _is_rate_limit_response(response):
            raise GitHubRateLimitError(_rate_limit_message(response, url))
        response.raise_for_status()
        mapped = map_issue_item(response.json(), repo_full_name)
        if mapped is None:
            raise ValueError("GitHub issue detail points to a pull request")
        return mapped

    def list_issue_comments(self, repo_full_name: str, issue_number: int) -> list[dict]:
        url = f"{GITHUB_API_URL}/repos/{repo_full_name}/issues/{issue_number}/comments"
        params = {"per_page": 100, "page": 1}
        results: list[dict] = []
        while True:
            response = self.session.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            items = response.json()
            if not items:
                break
            results.extend(map_comment_item(item) for item in items)
            if len(items) < params["per_page"]:
                break
            params["page"] += 1
        return results


def map_issue_item(item: dict, repo_full_name: str) -> dict | None:
    if "pull_request" in item:
        return None
    return {
        "github_issue_id": item["id"],
        "repo_full_name": repo_full_name,
        "issue_number": item["number"],
        "title": item["title"],
        "author_login": item.get("user", {}).get("login"),
        "state": item["state"],
        "comments_count": item.get("comments", 0),
        "html_url": item["html_url"],
        "issue_created_at": item["created_at"],
        "issue_updated_at": item["updated_at"],
    }


def map_comment_item(item: dict) -> dict:
    return {
        "github_comment_id": item["id"],
        "author_login": item.get("user", {}).get("login"),
        "comment_body": item.get("body"),
        "html_url": item.get("html_url"),
        "comment_created_at": item["created_at"],
        "comment_updated_at": item["updated_at"],
    }


def _is_rate_limit_response(response: requests.Response) -> bool:
    remaining = response.headers.get("X-RateLimit-Remaining")
    if remaining == "0":
        return True
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    message = str(payload.get("message", "")).lower()
    return "rate limit" in message


def _rate_limit_message(response: requests.Response, url: str) -> str:
    reset_at = _format_rate_limit_reset(response.headers.get("X-RateLimit-Reset"))
    if reset_at:
        return f"GitHub rate limit exceeded for url: {url}. Try again after {reset_at}."
    return f"GitHub rate limit exceeded for url: {url}"


def _format_rate_limit_reset(reset_epoch: str | None) -> str | None:
    if not reset_epoch:
        return None
    try:
        reset_time = datetime.fromtimestamp(int(reset_epoch), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
    return reset_time.isoformat().replace("+00:00", "Z")
