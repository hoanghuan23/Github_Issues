import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes_health import router as health_router
from app.api.routes_issues import router as issues_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_metrics import router as metrics_router
from app.api.routes_sources import router as sources_router
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.database import init_db
from app.services.scheduler_service import SchedulerService


logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logging.getLogger("watchfiles").setLevel(logging.WARNING)
logging.getLogger("watchfiles.main").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def run_due_scheduler_once(batch_size: int) -> None:
    with SessionLocal() as db:
        SchedulerService().run_due(db, batch_size)


async def run_scheduler_loop(interval_seconds: int, batch_size: int) -> None:
    while True:
        try:
            await asyncio.to_thread(run_due_scheduler_once, batch_size)
        except Exception:
            logger.exception("Scheduled due crawl failed")
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    scheduler_task = asyncio.create_task(
        run_scheduler_loop(
            settings.scheduler_interval_seconds,
            settings.scheduler_batch_size,
        )
    )
    try:
        yield
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    app = FastAPI(title="GitHub Issues Crawler", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(sources_router)
    app.include_router(issues_router)
    app.include_router(metrics_router)
    app.include_router(jobs_router)
    return app


app = create_app()
