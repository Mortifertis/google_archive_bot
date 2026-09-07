"""Tests for downloading Telegram photos without network access."""

import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from io import BytesIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from app.telegram_media import TelegramMediaError, download_message_photo


def async_test(
    function: Callable[[], Coroutine[Any, Any, None]],
) -> Callable[[], None]:
    """Run an async test without an async pytest plugin."""

    @wraps(function)
    def wrapper() -> None:
        asyncio.run(function())

    return wrapper


def _message(photos: list[dict[str, object]] | None = None) -> Message:
    payload: dict[str, object] = {
        "message_id": 42,
        "date": 1788806400,
        "chat": {"id": 123, "type": "private", "first_name": "Owner"},
    }
    if photos is not None:
        payload["photo"] = photos
    return Message.model_validate(payload)


def _photo(
    file_id: str,
    width: int,
    height: int,
    file_size: int | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "file_id": file_id,
        "file_unique_id": f"unique-{file_id}",
        "width": width,
        "height": height,
    }
    if file_size is not None:
        result["file_size"] = file_size
    return result


@async_test
async def test_largest_photo_is_downloaded_and_bytes_are_returned() -> None:
    message = _message(
        [
            _photo("small", 320, 240),
            _photo("largest", 1280, 960),
            _photo("medium", 800, 600),
        ]
    )
    bot = MagicMock()
    bot.download = AsyncMock(return_value=BytesIO(b"image bytes"))

    photo = await download_message_photo(bot, message)

    selected = bot.download.await_args.args[0]
    assert selected.file_id == "largest"
    assert photo.data == b"image bytes"
    assert (photo.width, photo.height) == (1280, 960)


@async_test
async def test_missing_file_size_does_not_prevent_selection() -> None:
    message = _message(
        [_photo("first", 100, 100), _photo("second", 200, 200)]
    )
    bot = MagicMock()
    bot.download = AsyncMock(return_value=BytesIO(b"data"))

    await download_message_photo(bot, message)

    assert bot.download.await_args.args[0].file_id == "second"


@async_test
async def test_message_without_photo_is_rejected() -> None:
    with pytest.raises(TelegramMediaError, match="does not contain"):
        await download_message_photo(MagicMock(), _message())


@async_test
async def test_none_download_result_is_rejected() -> None:
    bot = MagicMock()
    bot.download = AsyncMock(return_value=None)

    with pytest.raises(TelegramMediaError, match="no photo stream"):
        await download_message_photo(
            bot,
            _message([_photo("photo", 100, 100)]),
        )


@async_test
async def test_download_exception_is_wrapped() -> None:
    bot = MagicMock()
    bot.download = AsyncMock(side_effect=RuntimeError("Telegram failure"))

    with pytest.raises(TelegramMediaError, match="Could not download"):
        await download_message_photo(
            bot,
            _message([_photo("photo", 100, 100)]),
        )
