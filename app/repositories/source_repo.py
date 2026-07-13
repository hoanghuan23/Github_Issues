from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time_utils import to_naive_utc
from app.db.models import Source


def get_or_create_source(
    db: Session,
    source_type: str,
    identifier: str,
    display_name: str | None,
    include_comments: bool,
) -> tuple[Source, bool]:
    source = db.scalar(
        select(Source).where(
            Source.source_type == source_type,
            Source.identifier == identifier,
        )
    )
    if source:
        source.include_comments = include_comments
        source.display_name = display_name
        return source, False

    source = Source(
        source_type=source_type,
        identifier=identifier,
        display_name=display_name,
        include_comments=include_comments,
    )
    db.add(source)
    db.flush()
    return source, True


def get_or_create_repo_source(
    db: Session,
    identifier: str,
    include_comments: bool,
) -> tuple[Source, bool]:
    return get_or_create_source(db, "repo", identifier, identifier, include_comments)


def get_source(db: Session, source_id: int) -> Source | None:
    return db.get(Source, source_id)


def list_sources(db: Session) -> list[Source]:
    return list(db.scalars(select(Source).order_by(Source.id.desc())))


def due_sources(db: Session, now: datetime, limit: int = 50) -> list[Source]:
    return list(
        db.scalars(
            select(Source)
            .where(
                Source.is_active == True,  # noqa: E712
                Source.is_accessible == True,  # noqa: E712
                Source.next_scrape <= to_naive_utc(now),
            )
            .order_by(Source.next_scrape.asc())
            .limit(limit)
        )
    )
