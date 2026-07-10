from datetime import timedelta

from app.core.time_utils import utc_now
from app.services.scheduler_service import (
    calculate_issue_metric_interval_minutes,
    calculate_metric_tier,
    calculate_source_score,
    calculate_source_tier,
)


def test_metric_tier_from_comments_count():
    assert calculate_metric_tier(8) == "hot"
    assert calculate_metric_tier(4) == "high"
    assert calculate_metric_tier(2) == "medium"
    assert calculate_metric_tier(1) == "low"
    assert calculate_metric_tier(0) == "very_low"


def test_issue_metric_interval_by_tier_and_age():
    now = utc_now()
    assert calculate_issue_metric_interval_minutes("hot", now - timedelta(hours=1), now) == 15
    assert calculate_issue_metric_interval_minutes("hot", now - timedelta(hours=3), now) == 30
    assert calculate_issue_metric_interval_minutes("medium", now - timedelta(hours=8), now) == 180
    assert calculate_issue_metric_interval_minutes("very_low", now - timedelta(hours=18), now) == 360
    assert calculate_issue_metric_interval_minutes("low", now - timedelta(hours=25), now) is None


def test_source_score_and_tier():
    assert calculate_source_score(4, 0) == 8
    assert calculate_source_tier(7) == 1
    assert calculate_source_tier(8) == 2
    assert calculate_source_tier(20) == 3
    assert calculate_source_tier(40) == 4
    assert calculate_source_tier(80) == 5

