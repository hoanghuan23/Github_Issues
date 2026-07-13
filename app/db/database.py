from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _connect_args(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


engine = create_engine(
    get_settings().database_url,
    connect_args=_connect_args(get_settings().database_url),
    future=True,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()


def ensure_schema_compatibility() -> None:
    if not get_settings().database_url.startswith("sqlite"):
        return

    with engine.begin() as connection:
        issue_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(issues)")).fetchall()
        }
        if "labels_json" not in issue_columns:
            connection.execute(text("ALTER TABLE issues ADD COLUMN labels_json TEXT"))
        if "metric_tier" in issue_columns:
            connection.execute(
                text("UPDATE issues SET metric_tier = 'very_low' WHERE metric_tier = 'bootstrap'")
            )

        pipeline_log_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(pipeline_logs)")).fetchall()
        }
        if "error_details" not in pipeline_log_columns:
            connection.execute(text("ALTER TABLE pipeline_logs ADD COLUMN error_details TEXT"))
