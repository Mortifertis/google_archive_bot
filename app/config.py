"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass
from math import isfinite

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Config:
    """Settings required to run the bot."""

    bot_token: str
    owner_user_id: int
    media_group_debounce_seconds: float


@dataclass(frozen=True, slots=True)
class GoogleConfig:
    """Settings used by the standalone Google authorization command."""

    credentials_path: str
    token_path: str
    archive_folder_name: str


def load_google_config() -> GoogleConfig:
    """Load Google settings without requiring Telegram credentials."""
    load_dotenv()

    return GoogleConfig(
        credentials_path=os.getenv(
            "GOOGLE_CREDENTIALS_PATH",
            "google_credentials.json",
        ).strip()
        or "google_credentials.json",
        token_path=os.getenv(
            "GOOGLE_TOKEN_PATH",
            "google_token.json",
        ).strip()
        or "google_token.json",
        archive_folder_name=os.getenv(
            "GOOGLE_ARCHIVE_FOLDER_NAME",
            "Telegram Archive",
        ).strip()
        or "Telegram Archive",
    )


def load_config() -> Config:
    """Load and validate settings from a local ``.env`` file."""
    load_dotenv()

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    owner_user_id = os.getenv("OWNER_TELEGRAM_USER_ID", "").strip()
    debounce_value = os.getenv(
        "MEDIA_GROUP_DEBOUNCE_SECONDS",
        "1.5",
    ).strip()

    if not bot_token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN is missing. Add it to the .env file."
        )
    if not owner_user_id:
        raise ValueError(
            "OWNER_TELEGRAM_USER_ID is missing. Add it to the .env file."
        )

    try:
        parsed_owner_user_id = int(owner_user_id)
    except ValueError as error:
        raise ValueError(
            "OWNER_TELEGRAM_USER_ID must be an integer."
        ) from error

    try:
        media_group_debounce_seconds = float(debounce_value)
    except ValueError as error:
        raise ValueError(
            "MEDIA_GROUP_DEBOUNCE_SECONDS must be a number greater than 0."
        ) from error
    if (
        not isfinite(media_group_debounce_seconds)
        or media_group_debounce_seconds <= 0
    ):
        raise ValueError(
            "MEDIA_GROUP_DEBOUNCE_SECONDS must be greater than 0."
        )

    return Config(
        bot_token=bot_token,
        owner_user_id=parsed_owner_user_id,
        media_group_debounce_seconds=media_group_debounce_seconds,
    )
