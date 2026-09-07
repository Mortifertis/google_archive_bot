"""Download Telegram photos into short-lived in-memory values."""

import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import Message

logger = logging.getLogger(__name__)


class TelegramMediaError(RuntimeError):
    """A Telegram photo could not be selected or downloaded."""


@dataclass(frozen=True, slots=True)
class DownloadedPhoto:
    """An immutable Telegram photo kept in memory for one archive operation."""

    data: bytes
    width: int
    height: int
    file_unique_id: str


async def download_message_photo(
    bot: Bot,
    message: Message,
) -> DownloadedPhoto:
    """Download the largest photo variant attached to ``message``."""
    if not message.photo:
        raise TelegramMediaError("Message does not contain a photo")

    photo = max(
        message.photo,
        key=lambda item: (
            item.width * item.height,
            item.file_size or 0,
        ),
    )
    logger.info(
        "Starting Telegram photo download: message_id=%s, size=%sx%s",
        message.message_id,
        photo.width,
        photo.height,
    )
    try:
        stream = await bot.download(photo)
        if stream is None:
            raise TelegramMediaError("Telegram returned no photo stream")
        stream.seek(0)
        data = stream.read()
    except TelegramMediaError:
        raise
    except Exception as error:
        raise TelegramMediaError(
            "Could not download Telegram photo"
        ) from error

    if not isinstance(data, bytes):
        data = bytes(data)
    return DownloadedPhoto(
        data=data,
        width=photo.width,
        height=photo.height,
        file_unique_id=photo.file_unique_id,
    )
