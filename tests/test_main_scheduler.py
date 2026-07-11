import asyncio

import pytest

from app.main import run_due_scheduler_once, run_scheduler_loop


def test_run_due_scheduler_once_opens_session_and_runs_scheduler(monkeypatch):
    calls = []

    class FakeSessionContext:
        def __enter__(self):
            return "db-session"

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakeSchedulerService:
        def run_due(self, db, batch_size):
            calls.append((db, batch_size))

    monkeypatch.setattr("app.main.SessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr("app.main.SchedulerService", lambda: FakeSchedulerService())

    run_due_scheduler_once(batch_size=25)

    assert calls == [("db-session", 25)]


def test_scheduler_loop_runs_due_sources_before_waiting(monkeypatch):
    calls = []

    def fake_run_due_scheduler_once(batch_size):
        calls.append(batch_size)

    async def fake_sleep(interval_seconds):
        assert interval_seconds == 7
        raise asyncio.CancelledError

    monkeypatch.setattr("app.main.run_due_scheduler_once", fake_run_due_scheduler_once)
    monkeypatch.setattr("app.main.asyncio.sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_scheduler_loop(interval_seconds=7, batch_size=25))

    assert calls == [25]
