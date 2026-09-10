"""Focused regression tests for Telegram video and animation support."""

import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from app.media_group import is_supported_media_group
from app.telegram_media import (TELEGRAM_CLOUD_DOWNLOAD_LIMIT_BYTES,
                                TELEGRAM_DOWNLOAD_LIMIT_REASON,
                                TelegramMediaError, download_message_media)
from app.telegram_parser import parse_forwarded_messages


def _payload(message_id: int, kind: str, *, size: int = 100) -> dict:
    media = {
        "file_id": f"{kind}-{message_id}",
        "file_unique_id": f"unique-{kind}-{message_id}",
        "width": 640,
        "height": 360,
        "duration": 65,
        "file_size": size,
        "file_name": f"original-{message_id}.mp4",
        "mime_type": "video/mp4",
        "thumbnail": {
            "file_id": f"thumb-{message_id}",
            "file_unique_id": f"unique-thumb-{message_id}",
            "width": 320,
            "height": 180,
        },
    }
    return {
        "message_id": message_id,
        "date": 1788806400,
        "chat": {"id": 123, "type": "private", "first_name": "Owner"},
        "media_group_id": "album",
        "forward_origin": {
            "type": "channel",
            "date": 1788799200,
            "chat": {"id": -1001, "type": "channel", "title": "Channel"},
            "message_id": 500,
        },
        kind: media,
    }


def test_video_binary_metadata_and_thumbnail_are_preserved() -> None:
    async def run() -> None:
        message = Message.model_validate(_payload(1, "video"))
        bot = MagicMock()
        bot.download = AsyncMock(
            side_effect=[BytesIO(b"preview"), BytesIO(b"video")]
        )

        media = await download_message_media(bot, message)

        assert media.kind == "video"
        assert media.data == b"video"
        assert media.preview_data == b"preview"
        assert media.duration == 65
        assert media.file_name == "original-1.mp4"
        assert media.mime_type == "video/mp4"

    asyncio.run(run())


def test_animation_bytes_are_not_transcoded() -> None:
    async def run() -> None:
        payload = _payload(2, "animation")
        payload["animation"]["file_name"] = "original.gif"
        payload["animation"]["mime_type"] = "image/gif"
        message = Message.model_validate(payload)
        bot = MagicMock()
        bot.download = AsyncMock(
            side_effect=[BytesIO(b"thumb"), BytesIO(b"GIF89a")]
        )

        media = await download_message_media(bot, message)

        assert media.kind == "animation"
        assert media.data == b"GIF89a"
        assert media.mime_type == "image/gif"

    asyncio.run(run())


def test_oversized_video_skips_binary_but_downloads_thumbnail() -> None:
    async def run() -> None:
        message = Message.model_validate(
            _payload(
                3,
                "video",
                size=TELEGRAM_CLOUD_DOWNLOAD_LIMIT_BYTES + 1,
            )
        )
        bot = MagicMock()
        bot.download = AsyncMock(return_value=BytesIO(b"preview"))

        media = await download_message_media(bot, message)

        assert media.data is None
        assert media.preview_data == b"preview"
        assert media.unavailable_reason == TELEGRAM_DOWNLOAD_LIMIT_REASON
        bot.download.assert_awaited_once()

    asyncio.run(run())


def test_thumbnail_failure_is_non_fatal() -> None:
    async def run() -> None:
        message = Message.model_validate(_payload(4, "video"))
        bot = MagicMock()
        bot.download = AsyncMock(
            side_effect=[RuntimeError("thumbnail"), BytesIO(b"video")]
        )

        media = await download_message_media(bot, message)

        assert media.data == b"video"
        assert media.preview_data is None

    asyncio.run(run())


def test_real_binary_download_error_is_wrapped() -> None:
    async def run() -> None:
        payload = _payload(5, "video")
        payload["video"].pop("thumbnail")
        message = Message.model_validate(payload)
        bot = MagicMock()
        bot.download = AsyncMock(side_effect=RuntimeError("network"))
        with pytest.raises(TelegramMediaError):
            await download_message_media(bot, message)

    asyncio.run(run())


def test_mixed_groups_and_counts_preserve_input_kinds() -> None:
    photo = _payload(1, "video")
    photo.pop("video")
    photo["photo"] = [
        {
            "file_id": "photo",
            "file_unique_id": "unique-photo",
            "width": 100,
            "height": 100,
        }
    ]
    messages = [
        Message.model_validate(photo),
        Message.model_validate(_payload(2, "video")),
        Message.model_validate(_payload(3, "animation")),
    ]

    assert is_supported_media_group(messages)
    post = parse_forwarded_messages(messages)
    assert post is not None
    assert (post.photo_count, post.video_count, post.animation_count) == (
        1,
        1,
        1,
    )
    assert post.media_count == 3


def test_group_with_document_is_unsupported() -> None:
    document = Message.model_validate(
        {
            **_payload(2, "video"),
            "video": None,
            "document": {
                "file_id": "document",
                "file_unique_id": "unique-document",
            },
        }
    )
    assert not is_supported_media_group(
        [Message.model_validate(_payload(1, "video")), document]
    )
