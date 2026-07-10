COMMENT_TIER_THRESHOLDS = (
    (7, "hot"),
    (4, "high"),
    (2, "medium"),
    (1, "low"),
)

ISSUE_METRIC_INTERVAL_MINUTES = {
    "hot": ((2, 15), (6, 30), (12, 60), (24, 120)),
    "high": ((2, 30), (6, 60), (12, 120), (24, 180)),
    "medium": ((2, 45), (6, 90), (12, 180), (24, 240)),
    "low": ((2, 60), (6, 120), (12, 240), (24, 360)),
    "very_low": ((2, 60), (6, 120), (12, 240), (24, 360)),
}

SOURCE_TIER_THRESHOLDS = (
    (80, 5),
    (40, 4),
    (20, 3),
    (8, 2),
)

SOURCE_INTERVAL_MINUTES = {
    5: 10,
    4: 20,
    3: 30,
    2: 60,
    1: 120,
}

