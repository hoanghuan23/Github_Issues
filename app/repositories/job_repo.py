from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time_utils import to_naive_utc
from app.db.models import PipelineJob, PipelineLog


def create_job(db: Session, job_type: str, source_id: int | None = None, now: datetime | None = None) -> PipelineJob:
    job = PipelineJob(
        job_type=job_type,
        source_id=source_id,
        status="running",
        started_at=to_naive_utc(now) if now else None,
    )
    db.add(job)
    db.flush()
    return job


def finish_job(
    db: Session,
    job: PipelineJob,
    status: str,
    now: datetime,
    error_message: str | None = None,
) -> PipelineJob:
    job.status = status
    job.finished_at = to_naive_utc(now)
    job.error_message = error_message
    return job


def add_log(
    db: Session,
    message: str,
    log_level: str = "ERROR",
    job_id: int | None = None,
    source_id: int | None = None,
    error_type: str | None = None,
    error_details: str | None = None,
) -> PipelineLog:
    log = PipelineLog(
        job_id=job_id,
        source_id=source_id,
        log_level=log_level,
        message=message,
        error_type=error_type,
        error_details=error_details,
    )
    db.add(log)
    return log


def list_jobs(db: Session) -> list[PipelineJob]:
    return list(db.scalars(select(PipelineJob).order_by(PipelineJob.created_at.desc())))

