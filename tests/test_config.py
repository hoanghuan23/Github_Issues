from pathlib import Path

import pytest

from app.core import config
from app.services.github_client import GitHubClient


@pytest.fixture(autouse=True)
def clear_settings_cache():
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_get_settings_reads_github_token_from_dotenv(monkeypatch, tmp_path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "\n".join(
            [
                "GITHUB_TOKEN=dotenv-token",
                "SCHEDULER_INTERVAL_SECONDS=15",
                "SCHEDULER_BATCH_SIZE=3",
            ]
        )
    )

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("SCHEDULER_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("SCHEDULER_BATCH_SIZE", raising=False)
    monkeypatch.setattr(config, "PROJECT_ROOT", Path(tmp_path))
    config.get_settings.cache_clear()

    settings = config.get_settings()

    assert settings.github_token == "dotenv-token"
    assert settings.scheduler_interval_seconds == 15
    assert settings.scheduler_batch_size == 3


def test_environment_variable_overrides_dotenv(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("GITHUB_TOKEN=dotenv-token")

    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    monkeypatch.setattr(config, "PROJECT_ROOT", Path(tmp_path))
    config.get_settings.cache_clear()

    assert config.get_settings().github_token == "env-token"


def test_github_client_uses_dotenv_token_in_authorization_header(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("GITHUB_TOKEN=dotenv-token")

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(config, "PROJECT_ROOT", Path(tmp_path))
    config.get_settings.cache_clear()

    client = GitHubClient()

    assert client._headers()["Authorization"] == "Bearer dotenv-token"
