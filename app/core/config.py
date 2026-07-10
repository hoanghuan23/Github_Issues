import os
from functools import lru_cache

from pydantic import BaseModel


class Settings(BaseModel):
    database_url: str = "sqlite:///./data/github_issues.db"
    github_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/github_issues.db"),
        github_token=os.getenv("GITHUB_TOKEN"),
    )

