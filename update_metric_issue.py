import json
import os
from urllib.parse import urlparse

import requests


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


def issue_output_row(issue: dict) -> dict:
    return {
        column: issue.get(column)
        for column in PRINT_ISSUE_COLUMNS
    }


def get_issue(issue_api_url: str) -> dict:
    parsed_url = urlparse(issue_api_url)
    path_parts = parsed_url.path.strip("/").split("/")

    # Ví dụ: /repos/microsoft/vscode/issues/325084
    if (
        parsed_url.netloc != "api.github.com"
        or len(path_parts) != 5
        or path_parts[0] != "repos"
        or path_parts[3] != "issues"
        or not path_parts[4].isdigit()
    ):
        raise ValueError(
            "issue_api_url phải có dạng "
            "https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
        )

    repo_full_name = f"{path_parts[1]}/{path_parts[2]}"

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Không bắt buộc với repository public, nhưng nên dùng để tăng rate limit.
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    response = requests.get(
        issue_api_url,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()

    item = response.json()

    # Endpoint /issues/{number} cũng có thể trả về Pull Request.
    if "pull_request" in item:
        raise ValueError("URL này trỏ tới Pull Request, không phải Issue")

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


if __name__ == "__main__":
    issue = get_issue(
        issue_api_url=(
            "https://api.github.com/repos/"
            "microsoft/vscode/issues/325084"
        )
    )

    print(json.dumps(
        issue_output_row(issue),
        ensure_ascii=False,
        indent=2,
    ))