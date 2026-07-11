from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.schemas import JobRead
from app.services.metric_service import MetricService


router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.post("/due/run", response_model=list[JobRead])
def run_due_metrics(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return MetricService().run_due_metrics(db, limit)
