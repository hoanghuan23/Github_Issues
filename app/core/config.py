import os
from functools import lru_cache

from pydantic import BaseModel


class Settings(BaseModel):
    database_url: str = "sqlite:///./data/github_issues.db"
    github_token: str | None = None
    scheduler_interval_seconds: int = 120
    scheduler_batch_size: int = 50


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/github_issues.db"),
        github_token=os.getenv("GITHUB_TOKEN"),
        scheduler_interval_seconds=int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "120")),
        scheduler_batch_size=int(os.getenv("SCHEDULER_BATCH_SIZE", "50")),
    )
