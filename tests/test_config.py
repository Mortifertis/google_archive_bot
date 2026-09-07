"""Tests for application configuration."""

import pytest

from app.config import load_config, load_google_config


def _required_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("OWNER_TELEGRAM_USER_ID", "123")


def test_default_media_group_debounce(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_environment(monkeypatch)
    monkeypatch.delenv("MEDIA_GROUP_DEBOUNCE_SECONDS", raising=False)

    assert load_config().media_group_debounce_seconds == 1.5


def test_custom_media_group_debounce(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_environment(monkeypatch)
    monkeypatch.setenv("MEDIA_GROUP_DEBOUNCE_SECONDS", "2")

    assert load_config().media_group_debounce_seconds == 2.0


@pytest.mark.parametrize("value", ("0", "abc"))
def test_invalid_media_group_debounce(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    _required_environment(monkeypatch)
    monkeypatch.setenv("MEDIA_GROUP_DEBOUNCE_SECONDS", value)

    with pytest.raises(ValueError, match="MEDIA_GROUP_DEBOUNCE_SECONDS"):
        load_config()


def test_google_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_TOKEN_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_ARCHIVE_FOLDER_NAME", raising=False)

    config = load_google_config()

    assert config.credentials_path == "google_credentials.json"
    assert config.token_path == "google_token.json"
    assert config.archive_folder_name == "Telegram Archive"
