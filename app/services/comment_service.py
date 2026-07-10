from datetime import datetime

from sqlalchemy.orm import Session

from app.repositories.comment_repo import upsert_comments
from app.services.github_client import GitHubClient


def maybe_fetch_comments(
    github_client: GitHubClient,
    repo_full_name: str,
    issue_number: int,
    include_comments: bool,
    is_new_issue: bool,
    comments_increased: bool,
) -> list[dict]:
    if not include_comments:
        return []
    if not is_new_issue and not comments_increased:
        return []
    return github_client.list_issue_comments(repo_full_name, issue_number)


def save_comments(db: Session, issue_id: int, comments: list[dict], now: datetime) -> tuple[int, int]:
    if not comments:
        return 0, 0
    return upsert_comments(db, issue_id, comments, now)

