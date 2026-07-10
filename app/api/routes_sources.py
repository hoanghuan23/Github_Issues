from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.schemas import SourceCreate, SourceCreateResponse, SourceRead
from app.repositories.source_repo import get_source, list_sources
from app.services.source_service import SourceService


router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("", response_model=SourceCreateResponse)
def create_source(payload: SourceCreate, db: Session = Depends(get_db)):
    try:
        source, job = SourceService().create_source_and_scrape(
            db,
            payload.url,
            payload.include_comments,
        )
        return {"source": source, "job": job}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[SourceRead])
def sources(db: Session = Depends(get_db)):
    return list_sources(db)


@router.get("/{source_id}", response_model=SourceRead)
def source_detail(source_id: int, db: Session = Depends(get_db)):
    source = get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    return source


@router.post("/{source_id}/scrape", response_model=SourceCreateResponse)
def scrape_source(source_id: int, db: Session = Depends(get_db)):
    try:
        source, job = SourceService().scrape_source(db, source_id)
        return {"source": source, "job": job}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

