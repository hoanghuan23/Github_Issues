from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db import database
from app.db.database import Base, ensure_schema_compatibility
from app.db.models import PipelineLog


class SQLiteSettings:
    database_url = "sqlite:///compatibility-test.db"


def test_ensure_schema_compatibility_adds_pipeline_log_error_details(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'compatibility.db'}", future=True)
    Base.metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(text("DROP TABLE pipeline_logs"))
        connection.execute(
            text(
                """
                CREATE TABLE pipeline_logs (
                    id INTEGER PRIMARY KEY,
                    job_id INTEGER REFERENCES pipeline_jobs(id) ON DELETE SET NULL,
                    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
                    log_level VARCHAR(20) NOT NULL DEFAULT 'ERROR',
                    message TEXT NOT NULL,
                    error_type VARCHAR(100),
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "get_settings", lambda: SQLiteSettings())

    ensure_schema_compatibility()

    with engine.connect() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(pipeline_logs)")).fetchall()
        }
    assert "error_details" in columns

    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestingSessionLocal() as db:
        db.add(
            PipelineLog(
                log_level="ERROR",
                message="failed",
                error_type="HTTPError",
                error_details="rate limited",
            )
        )
        db.commit()
