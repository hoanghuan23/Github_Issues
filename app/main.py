from fastapi import FastAPI

from app.api.routes_health import router as health_router
from app.api.routes_issues import router as issues_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_metrics import router as metrics_router
from app.api.routes_sources import router as sources_router
from app.db.database import init_db


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(title="GitHub Issues Crawler")
    app.include_router(health_router)
    app.include_router(sources_router)
    app.include_router(issues_router)
    app.include_router(metrics_router)
    app.include_router(jobs_router)
    return app


app = create_app()

