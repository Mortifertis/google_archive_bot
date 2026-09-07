"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Config:
    """Settings required to run the bot."""

    bot_token: str
    owner_user_id: int


def load_config() -> Config:
    """Load and validate settings from a local ``.env`` file."""
    load_dotenv()

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    owner_user_id = os.getenv("OWNER_TELEGRAM_USER_ID", "").strip()

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

    return Config(
        bot_token=bot_token,
        owner_user_id=parsed_owner_user_id,
    )
