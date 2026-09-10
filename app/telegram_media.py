"""Download supported Telegram media into short-lived memory values."""

import logging
from dataclasses import dataclass
from typing import Literal

from aiogram import Bot
from aiogram.types import Message

logger = logging.getLogger(__name__)

TELEGRAM_CLOUD_DOWNLOAD_LIMIT_BYTES = 20 * 1024 * 1024
TELEGRAM_DOWNLOAD_LIMIT_REASON = "telegram_download_limit"
MediaKind = Literal["photo", "video", "animation"]


class TelegramMediaError(RuntimeError):
    """A Telegram media file could not be selected or downloaded."""


@dataclass(frozen=True, slots=True)
class DownloadedMedia:
    """A supported Telegram media item held in memory for one operation."""

    kind: MediaKind
    data: bytes | None
    preview_data: bytes | None
    width: int | None
    height: int | None
    duration: int | None
    file_unique_id: str
    file_name: str | None
    mime_type: str | None
    file_size: int | None
    unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ArchivedMedia:
    """Media representation ready to be rendered in an archive document."""

    kind: MediaKind
    preview_data: bytes | None
    width: int | None
    height: int | None
    duration: int | None
    file_size: int | None
    mime_type: str | None = None
    drive_web_url: str | None = None
    unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadedPhoto:
    """Legacy photo value accepted by the public document builder API."""

    data: bytes
    width: int
    height: int
    file_unique_id: str


async def _download_bytes(bot: Bot, downloadable: object) -> bytes:
    stream = await bot.download(downloadable)
    if stream is None:
        raise TelegramMediaError("Telegram returned no media stream")
    stream.seek(0)
    data = stream.read()
    return data if isinstance(data, bytes) else bytes(data)


async def download_message_photo(
    bot: Bot,
    message: Message,
) -> DownloadedMedia:
    """Download the largest photo variant attached to ``message``."""
    if not message.photo:
        raise TelegramMediaError("Message does not contain a photo")
    photo = max(
        message.photo,
        key=lambda item: (item.width * item.height, item.file_size or 0),
    )
    try:
        data = await _download_bytes(bot, photo)
    except TelegramMediaError as error:
        raise TelegramMediaError(
            str(error).replace("media stream", "photo stream")
        ) from error
    except Exception as error:
        raise TelegramMediaError(
            "Could not download Telegram photo"
        ) from error
    return DownloadedMedia(
        kind="photo",
        data=data,
        preview_data=None,
        width=photo.width,
        height=photo.height,
        duration=None,
        file_unique_id=photo.file_unique_id,
        file_name=None,
        mime_type="image/jpeg",
        file_size=photo.file_size,
    )


def _is_too_big_error(error: Exception) -> bool:
    text = str(error).casefold()
    return "file is too big" in text or "file too big" in text


async def _download_preview(
    bot: Bot,
    media: object,
    message_id: int,
) -> bytes | None:
    thumbnail = getattr(media, "thumbnail", None)
    if thumbnail is None:
        return None
    try:
        return await _download_bytes(bot, thumbnail)
    except Exception:
        logger.warning(
            "Could not download Telegram media thumbnail: message_id=%s",
            message_id,
            exc_info=True,
        )
        return None


async def download_message_media(
    bot: Bot,
    message: Message,
) -> DownloadedMedia:
    """Download one supported media item, preserving Telegram metadata."""
    if message.photo:
        return await download_message_photo(bot, message)
    kind: MediaKind
    if message.video is not None:
        kind = "video"
        media = message.video
    elif message.animation is not None:
        kind = "animation"
        media = message.animation
    else:
        raise TelegramMediaError("Message has no supported media")

    preview_data = await _download_preview(bot, media, message.message_id)
    unavailable_reason = None
    data = None
    if (
        media.file_size is not None
        and media.file_size > TELEGRAM_CLOUD_DOWNLOAD_LIMIT_BYTES
    ):
        unavailable_reason = TELEGRAM_DOWNLOAD_LIMIT_REASON
    else:
        try:
            data = await _download_bytes(bot, media)
        except Exception as error:
            if _is_too_big_error(error):
                unavailable_reason = TELEGRAM_DOWNLOAD_LIMIT_REASON
            else:
                raise TelegramMediaError(
                    f"Could not download Telegram {kind}"
                ) from error

    return DownloadedMedia(
        kind=kind,
        data=data,
        preview_data=preview_data,
        width=media.width,
        height=media.height,
        duration=media.duration,
        file_unique_id=media.file_unique_id,
        file_name=media.file_name,
        mime_type=media.mime_type,
        file_size=media.file_size,
        unavailable_reason=unavailable_reason,
    )
