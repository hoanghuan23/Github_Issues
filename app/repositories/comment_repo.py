from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time_utils import parse_github_datetime, to_naive_utc
from app.db.models import IssueComment


def upsert_comments(
    db: Session,
    issue_id: int,
    comments: list[dict],
    now: datetime,
) -> tuple[int, int]:
    found = len(comments)
    new_count = 0
    now_naive = to_naive_utc(now)
    for item in comments:
        comment = db.scalar(
            select(IssueComment).where(
                IssueComment.github_comment_id == item["github_comment_id"]
            )
        )
        if comment is None:
            comment = IssueComment(
                issue_id=issue_id,
                github_comment_id=item["github_comment_id"],
                comment_created_at=to_naive_utc(parse_github_datetime(item["comment_created_at"])),
                comment_updated_at=to_naive_utc(parse_github_datetime(item["comment_updated_at"])),
            )
            db.add(comment)
            new_count += 1
        comment.author_login = item["author_login"]
        comment.comment_body = item["comment_body"]
        comment.html_url = item["html_url"]
        comment.comment_updated_at = to_naive_utc(parse_github_datetime(item["comment_updated_at"]))
        comment.last_seen_at = now_naive
    return found, new_count

