"""Tests for collecting Telegram media groups."""

import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any

import pytest
from aiogram.types import Message

from app.media_group import MediaGroupCollector, is_photo_album
from app.telegram_parser import parse_forwarded_messages


def async_test(
    function: Callable[[], Coroutine[Any, Any, None]],
) -> Callable[[], None]:
    """Run an async test without requiring an additional pytest plugin."""

    @wraps(function)
    def wrapper() -> None:
        asyncio.run(function())

    return wrapper


def _message(
    message_id: int,
    group_id: str | None = "album-1",
    *,
    photo: bool = False,
    caption: str | None = None,
) -> Message:
    payload: dict = {
        "message_id": message_id,
        "date": 1788806400,
        "chat": {"id": 123, "type": "private", "first_name": "Owner"},
        "media_group_id": group_id,
        "forward_origin": {
            "type": "channel",
            "date": 1788799200,
            "chat": {
                "id": -1001234567890,
                "type": "channel",
                "title": "Some Channel",
                "username": "somechannel",
            },
            "message_id": 1000 + message_id,
        },
    }
    if photo:
        payload["photo"] = [
            {
                "file_id": f"photo-{message_id}",
                "file_unique_id": "unique",
                "width": 800,
                "height": 600,
            }
        ]
    if caption is not None:
        payload["caption"] = caption
    return Message.model_validate(payload)


def test_photo_album_is_supported() -> None:
    messages = [_message(item, photo=True) for item in range(1, 4)]

    assert is_photo_album(messages) is True


def test_mixed_media_album_is_not_supported() -> None:
    messages = [_message(1, photo=True), _message(2, photo=True)]
    video = _message(3).model_copy(
        update={
            "video": {
                "file_id": "video",
                "file_unique_id": "unique-video",
                "width": 800,
                "height": 600,
                "duration": 1,
            }
        }
    )

    assert is_photo_album([*messages, video]) is False


@async_test
async def test_two_messages_are_delivered_once() -> None:
    collector = MediaGroupCollector(0.01)
    calls: list[list[Message]] = []

    async def callback(messages: list[Message]) -> None:
        calls.append(messages)

    await collector.add(_message(1), callback)
    await collector.add(_message(2), callback)
    await asyncio.sleep(0.03)

    assert len(calls) == 1
    assert len(calls[0]) == 2
    await collector.close()


@async_test
async def test_five_photos_are_aggregated() -> None:
    collector = MediaGroupCollector(0.01)
    posts = []

    async def callback(messages: list[Message]) -> None:
        posts.append(parse_forwarded_messages(messages))

    for message_id in range(1, 6):
        await collector.add(_message(message_id, photo=True), callback)
    await asyncio.sleep(0.03)

    assert len(posts) == 1
    assert posts[0] is not None
    assert posts[0].photo_count == 5
    await collector.close()


@async_test
async def test_caption_from_first_item_is_preserved() -> None:
    collector = MediaGroupCollector(0.01)
    posts = []

    async def callback(messages: list[Message]) -> None:
        posts.append(parse_forwarded_messages(messages))

    await collector.add(_message(1, caption="Album caption"), callback)
    await collector.add(_message(2), callback)
    await asyncio.sleep(0.03)

    assert posts[0] is not None
    assert posts[0].caption == "Album caption"
    assert posts[0].text == "Album caption"
    assert posts[0].source_message_id == 1001
    await collector.close()


@async_test
async def test_messages_are_sorted_by_message_id() -> None:
    collector = MediaGroupCollector(0.01)
    received: list[int] = []

    async def callback(messages: list[Message]) -> None:
        received.extend(message.message_id for message in messages)

    for message_id in (103, 101, 102):
        await collector.add(_message(message_id), callback)
    await asyncio.sleep(0.03)

    assert received == [101, 102, 103]
    await collector.close()


@async_test
async def test_two_groups_are_kept_separate() -> None:
    collector = MediaGroupCollector(0.01)
    calls: list[tuple[str, list[int]]] = []

    async def callback(messages: list[Message]) -> None:
        calls.append(
            (
                messages[0].media_group_id or "",
                [message.message_id for message in messages],
            )
        )

    await collector.add(_message(1, "first"), callback)
    await collector.add(_message(3, "second"), callback)
    await collector.add(_message(2, "first"), callback)
    await collector.add(_message(4, "second"), callback)
    await asyncio.sleep(0.03)

    assert sorted(calls) == [("first", [1, 2]), ("second", [3, 4])]
    await collector.close()


@async_test
async def test_message_without_media_group_is_rejected() -> None:
    collector = MediaGroupCollector(0.01)

    async def callback(messages: list[Message]) -> None:
        raise AssertionError("callback must not run")

    with pytest.raises(ValueError, match="media_group_id"):
        await collector.add(_message(1, None), callback)
    await collector.close()


@async_test
async def test_close_cancels_pending_delivery() -> None:
    collector = MediaGroupCollector(10)
    called = False

    async def callback(messages: list[Message]) -> None:
        nonlocal called
        called = True

    await collector.add(_message(1), callback)
    await collector.close()

    assert called is False
