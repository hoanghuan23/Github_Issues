from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Issue
from app.db.schemas import IssueListResponse, IssueRead
from app.repositories.issue_repo import list_issues


router = APIRouter(prefix="/issues", tags=["issues"])


@router.get("", response_model=IssueListResponse)
def issues(
    repo_full_name: str | None = None,
    metric_tier: str | None = None,
    is_tracked: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return {
        "items": list_issues(db, repo_full_name, metric_tier, is_tracked, limit, offset),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{issue_id}", response_model=IssueRead)
def issue_detail(issue_id: int, db: Session = Depends(get_db)):
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="issue not found")
    return issue

