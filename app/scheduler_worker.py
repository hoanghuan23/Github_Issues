import time

from app.core.config import get_settings
from app.db.database import SessionLocal, init_db
from app.services.scheduler_service import SchedulerService


def run_scheduler_forever(
    interval_seconds: int | None = None,
    batch_size: int | None = None,
) -> None:
    settings = get_settings()
    poll_interval = (
        interval_seconds
        if interval_seconds is not None
        else settings.scheduler_interval_seconds
    )
    due_batch_size = (
        batch_size
        if batch_size is not None
        else settings.scheduler_batch_size
    )

    init_db()
    scheduler = SchedulerService()

    while True:
        with SessionLocal() as db:
            scheduler.run_due(db, due_batch_size)
        time.sleep(poll_interval)


if __name__ == "__main__":
    run_scheduler_forever()
