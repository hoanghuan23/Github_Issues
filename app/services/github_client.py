from dataclasses import dataclass
from datetime import datetime, timezone
from datetime import timedelta
import shlex
from urllib.parse import parse_qs, urlparse

import requests

from app.core.config import get_settings
from app.core.time_utils import ensure_aware_utc, parse_github_datetime, utc_now


GITHUB_API_URL = "https://api.github.com"


class GitHubNotFoundError(Exception):
    pass


class GitHubRateLimitError(Exception):
    pass


@dataclass(frozen=True)
class GitHubIssuesSource:
    source_type: str
    identifier: str
    display_name: str
    api_path: str
    params: dict[str, str]
    repo_full_name: str | None = None


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
    source = parse_github_source_url(url)
    if source.source_type != "repo" or source.repo_full_name is None:
        raise ValueError(
            "url must be https://github.com/{owner}/{repo}/issues"
        )
    owner, repo = source.repo_full_name.split("/", 1)
    return RepoIssuesSource(owner=owner, repo=repo)


def parse_github_source_url(url: str) -> GitHubIssuesSource:
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip("/").split("/")

    if (
        parsed_url.scheme == "https"
        and parsed_url.netloc == "github.com"
        and len(path_parts) == 3
        and path_parts[2] == "issues"
    ):
        repo_full_name = f"{path_parts[0]}/{path_parts[1]}"
        query_params = parse_qs(parsed_url.query)
        query = _single_query_param(query_params, "q")
        label = _label_from_search_query(query) if query else None
        if label:
            return source_from_type_identifier("label", f"{repo_full_name}:{label}")
        return source_from_type_identifier("repo", repo_full_name)

    if (
        parsed_url.scheme == "https"
        and parsed_url.netloc == "github.com"
        and path_parts == ["search"]
    ):
        query_params = parse_qs(parsed_url.query)
        query = _single_query_param(query_params, "q")
        if not query:
            raise ValueError("search source url must include q")
        source_type, identifier = _parse_search_query_source(query)
        return source_from_type_identifier(source_type, identifier)

    if parsed_url.scheme != "https" or parsed_url.netloc != "api.github.com":
        raise ValueError("unsupported GitHub source url")

    query_params = parse_qs(parsed_url.query)
    if len(path_parts) == 4 and path_parts[0] == "repos" and path_parts[3] == "issues":
        repo_full_name = f"{path_parts[1]}/{path_parts[2]}"
        labels = _single_query_param(query_params, "labels")
        if not labels:
            raise ValueError("label source url must include labels")
        return source_from_type_identifier("label", f"{repo_full_name}:{labels}")

    if len(path_parts) == 2 and path_parts == ["search", "issues"]:
        query = _single_query_param(query_params, "q")
        if not query:
            raise ValueError("search source url must include q")
        source_type, identifier = _parse_search_query_source(query)
        return source_from_type_identifier(source_type, identifier)

    raise ValueError("unsupported GitHub source url")


def source_from_type_identifier(source_type: str, identifier: str) -> GitHubIssuesSource:
    if source_type == "repo":
        owner, repo = _split_repo_identifier(identifier)
        repo_full_name = f"{owner}/{repo}"
        return GitHubIssuesSource(
            source_type="repo",
            identifier=repo_full_name,
            display_name=repo_full_name,
            api_path=f"repos/{repo_full_name}/issues",
            params={},
            repo_full_name=repo_full_name,
        )
    if source_type == "label":
        repo_full_name, label = _split_label_identifier(identifier)
        return GitHubIssuesSource(
            source_type="label",
            identifier=f"{repo_full_name}:{label}",
            display_name=f"{repo_full_name}:{label}",
            api_path=f"repos/{repo_full_name}/issues",
            params={"labels": label},
            repo_full_name=repo_full_name,
        )
    if source_type == "organization":
        return GitHubIssuesSource(
            source_type="organization",
            identifier=identifier,
            display_name=identifier,
            api_path="search/issues",
            params={"q": f"org:{identifier} is:issue state:open"},
        )
    if source_type == "keyword":
        query_keyword = f'"{identifier}"' if " " in identifier else identifier
        return GitHubIssuesSource(
            source_type="keyword",
            identifier=identifier,
            display_name=identifier,
            api_path="search/issues",
            params={"q": f"{query_keyword} is:issue state:open"},
        )
    raise ValueError(f"unsupported source_type: {source_type}")


def _single_query_param(query_params: dict[str, list[str]], name: str) -> str | None:
    values = query_params.get(name)
    if not values:
        return None
    return values[0].strip()


def _parse_search_query_source(query: str) -> tuple[str, str]:
    tokens = _search_query_tokens(query)

    for token in tokens:
        if token.startswith("org:") and token != "org:":
            return "organization", token.removeprefix("org:").strip()

    keyword_tokens = [
        token
        for token in tokens
        if token not in {"is:issue", "state:open"}
    ]
    keyword = " ".join(keyword_tokens).strip().strip('"')
    if not keyword:
        raise ValueError("keyword search source must include a keyword")
    return "keyword", keyword


def _label_from_search_query(query: str) -> str | None:
    for token in _search_query_tokens(query):
        if token.startswith("label:") and token != "label:":
            return token.removeprefix("label:").strip()
    return None


def _search_query_tokens(query: str) -> list[str]:
    try:
        return shlex.split(query)
    except ValueError:
        return query.split()


def _split_repo_identifier(identifier: str) -> tuple[str, str]:
    parts = identifier.split("/", 1)
    if len(parts) != 2 or not all(parts):
        raise ValueError("repo identifier must be owner/repo")
    return parts[0], parts[1]


def _split_label_identifier(identifier: str) -> tuple[str, str]:
    repo_full_name, separator, label = identifier.partition(":")
    if not separator or not repo_full_name or not label:
        raise ValueError("label identifier must be owner/repo:label")
    _split_repo_identifier(repo_full_name)
    return repo_full_name, label


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
        stop_at_created_at: datetime | None = None,
    ) -> list[dict]:
        return self.list_recent_source_issues(
            source_from_type_identifier("repo", source.identifier),
            max_hours_old=max_hours_old,
            stop_at_created_at=stop_at_created_at,
        )

    def list_recent_source_issues(
        self,
        source: GitHubIssuesSource,
        max_hours_old: int = 24,
        stop_at_created_at: datetime | None = None,
    ) -> list[dict]:
        url = f"{GITHUB_API_URL}/{source.api_path}"
        params = {
            "state": "open",
            "sort": "created",
            "direction": "desc",
            "per_page": 100,
            "page": 1,
        }
        if source.api_path == "search/issues":
            params.pop("state")
            params.pop("direction")
            params["order"] = "desc"
        params.update(source.params)
        cutoff = utc_now() - timedelta(hours=max_hours_old)
        stop_at = ensure_aware_utc(stop_at_created_at) if stop_at_created_at else None
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
            if isinstance(items, dict):
                items = items.get("items", [])

            reached_old_issue = False
            for item in items:
                repo_full_name = source.repo_full_name or repo_full_name_from_issue_item(item)
                mapped = map_issue_item(item, repo_full_name)
                if mapped is None:
                    continue
                issue_created_at = parse_github_datetime(mapped["issue_created_at"])
                if stop_at and issue_created_at <= stop_at:
                    reached_old_issue = True
                    break
                if issue_created_at < cutoff:
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


def repo_full_name_from_issue_item(item: dict) -> str:
    repository_url = item.get("repository_url")
    if repository_url:
        parsed_url = urlparse(repository_url)
        path_parts = parsed_url.path.strip("/").split("/")
        if (
            parsed_url.netloc == "api.github.com"
            and len(path_parts) == 3
            and path_parts[0] == "repos"
        ):
            return f"{path_parts[1]}/{path_parts[2]}"

    html_url = item.get("html_url", "")
    parsed_url = urlparse(html_url)
    path_parts = parsed_url.path.strip("/").split("/")
    if parsed_url.netloc == "github.com" and len(path_parts) >= 2:
        return f"{path_parts[0]}/{path_parts[1]}"

    raise ValueError("GitHub issue item does not include repository information")


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
