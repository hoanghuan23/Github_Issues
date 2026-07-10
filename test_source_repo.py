import json
import os
from datetime import datetime, timedelta, timezone

import requests


GITHUB_API_URL = "https://api.github.com"

PRINT_ISSUE_COLUMNS = [
    "github_issue_id",
    "repo_full_name",
    "issue_number",
    "title",
    "author_login",
    "state",
    "comments_count",
    "html_url",
    "issue_created_at",
    "issue_updated_at",
]


def parse_github_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def issue_output_row(issue: dict) -> dict:
    return {
        column: issue.get(column)
        for column in PRINT_ISSUE_COLUMNS
    }


def get_repo_issues(
    api_path: str,
    max_hours_old: int = 24,
) -> list[dict]:
    url = f"{GITHUB_API_URL}/{api_path.lstrip('/')}"

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Không bắt buộc với repository public, nhưng nên dùng để tăng rate limit.
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    params = {
        "state": "open",
        "sort": "created",
        "direction": "desc",
        "per_page": 100,
        "page": 1,
    }

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_hours_old)

    # repos/microsoft/vscode/issues
    path_parts = api_path.strip("/").split("/")

    if len(path_parts) < 4 or path_parts[0] != "repos":
        raise ValueError(
            "api_path phải có dạng repos/{owner}/{repo}/issues"
        )

    repo_full_name = f"{path_parts[1]}/{path_parts[2]}"

    results = []

    while True:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=30,
        )
        response.raise_for_status()

        items = response.json()

        if not items:
            break

        reached_old_issue = False

        for item in items:
            # Endpoint issues cũng trả về Pull Request.
            if "pull_request" in item:
                continue

            issue_created_at = parse_github_datetime(
                item["created_at"]
            )

            # Vì đang sort created DESC, gặp issue quá 24 giờ thì
            # các issue phía sau cũng đều cũ hơn.
            if issue_created_at < cutoff:
                reached_old_issue = True
                break

            issue_data = {
                "github_issue_id": item["id"],
                "repo_full_name": repo_full_name,
                "issue_number": item["number"],
                "title": item["title"],
                "body": item.get("body"),
                "author_login": (
                    item.get("user", {}).get("login")
                ),
                "state": item["state"],
                "comments_count": item.get("comments", 0),
                "html_url": item["html_url"],
                "issue_created_at": item["created_at"],
                "issue_updated_at": item["updated_at"],
            }

            results.append(issue_data)

        if reached_old_issue:
            break

        if len(items) < params["per_page"]:
            break

        params["page"] += 1

    return results


if __name__ == "__main__":
    issues = get_repo_issues(
        api_path="repos/microsoft/vscode/issues",
        max_hours_old=24,
    )

    print(f"Tìm thấy {len(issues)} issue mới trong 24 giờ")

    print(json.dumps(
        [issue_output_row(issue) for issue in issues],
        ensure_ascii=False,
        indent=2,
    ))
