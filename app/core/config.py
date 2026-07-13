import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseModel):
    database_url: str = "sqlite:///./data/github_issues.db"
    github_token: str | None = None
    scheduler_interval_seconds: int = 120
    scheduler_batch_size: int = 50


def _load_dotenv_values(path: Path | None = None) -> dict[str, str]:
    path = path or PROJECT_ROOT / ".env"
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _env(dotenv_values: dict[str, str], name: str, default: str | None = None) -> str | None:
    return os.getenv(name) or dotenv_values.get(name, default)


@lru_cache
def get_settings() -> Settings:
    dotenv_values = _load_dotenv_values()
    return Settings(
        database_url=_env(dotenv_values, "DATABASE_URL", "sqlite:///./data/github_issues.db"),
        github_token=_env(dotenv_values, "GITHUB_TOKEN"),
        scheduler_interval_seconds=int(_env(dotenv_values, "SCHEDULER_INTERVAL_SECONDS", "120")),
        scheduler_batch_size=int(_env(dotenv_values, "SCHEDULER_BATCH_SIZE", "50")),
    )
