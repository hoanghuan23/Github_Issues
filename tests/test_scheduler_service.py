import logging
from datetime import timedelta
from types import SimpleNamespace

from app.core.time_utils import to_naive_utc, utc_now
from app.db.models import Source
from app.repositories.source_repo import due_sources
from app.services.scheduler_service import SchedulerService


class FakeSourceService:
    def __init__(self):
        self.scraped_source_ids = []

    def scrape_source(self, db, source_id):
        self.scraped_source_ids.append(source_id)
        job = SimpleNamespace(issues_found=5, issues_new=5, items_failed=0)
        return None, job


class FakeMetricService:
    def __init__(self):
        self.limits = []

    def run_due_metrics(self, db, limit):
        self.limits.append(limit)
        return []


def add_source(
    db_session,
    identifier: str,
    next_scrape,
    is_active: bool = True,
    is_accessible: bool = True,
):
    source = Source(
        source_type="repo",
        identifier=identifier,
        display_name=identifier,
        is_active=is_active,
        is_accessible=is_accessible,
        next_scrape=to_naive_utc(next_scrape),
    )
    db_session.add(source)
    db_session.commit()
    return source


def test_due_sources_filters_orders_and_limits(db_session):
    now = utc_now()
    later_due = add_source(db_session, "acme/later", now - timedelta(minutes=5))
    first_due = add_source(db_session, "acme/first", now - timedelta(minutes=10))
    add_source(db_session, "acme/future", now + timedelta(minutes=10))
    add_source(db_session, "acme/inactive", now - timedelta(minutes=20), is_active=False)
    add_source(db_session, "acme/private", now - timedelta(minutes=20), is_accessible=False)

    sources = due_sources(db_session, now, limit=2)

    assert [source.id for source in sources] == [first_due.id, later_due.id]


def test_scheduler_run_due_scrapes_due_sources_and_runs_metric_batch(db_session, caplog):
    now = utc_now()
    due = add_source(db_session, "acme/due", now - timedelta(minutes=1))
    add_source(db_session, "acme/not-due", now + timedelta(minutes=1))
    source_service = FakeSourceService()
    metric_service = FakeMetricService()

    caplog.set_level(logging.INFO, logger="app.services.scheduler_service")
    result = SchedulerService(source_service, metric_service).run_due(db_session, batch_size=25)

    assert source_service.scraped_source_ids == [due.id]
    assert metric_service.limits == [25]
    assert result.sources_attempted == 1
    assert result.sources_failed == 0
    assert "Scheduler bat dau scrape bai moi | sources_due=1" in caplog.messages
    assert f"Bat dau scrape bai moi | source=due id={due.id} type=user max_count=25" in caplog.messages
    assert f"Hoan tat scrape bai moi | source=due id={due.id} found=5 new=5 failed=0" in caplog.messages
    assert (
        "Scheduler hoan tat chu ky | sources_processed=1 posts_processed=0 posts_expired=0"
        in caplog.messages
    )
