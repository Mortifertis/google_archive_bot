"""Tests for extracting forwarded Telegram post metadata."""

from datetime import datetime, timezone

from aiogram.types import Message

from app.telegram_parser import parse_forwarded_post


def _message_payload(
    *,
    channel_username: str | None = "somechannel",
    forwarded: bool = True,
) -> dict:
    channel = {
        "id": -1001234567890,
        "type": "channel",
        "title": "Some Channel",
    }
    if channel_username is not None:
        channel["username"] = channel_username

    payload = {
        "message_id": 10,
        "date": 1788806400,
        "chat": {"id": 123, "type": "private", "first_name": "Owner"},
        "text": "Forwarded text",
    }
    if forwarded:
        payload["forward_origin"] = {
            "type": "channel",
            "date": 1788799200,
            "chat": channel,
            "message_id": 12345,
        }
    return payload


def test_public_channel_forward() -> None:
    message = Message.model_validate(_message_payload())

    post = parse_forwarded_post(message)

    assert post is not None
    assert post.is_channel_post is True
    assert post.source_chat_title == "Some Channel"
    assert post.source_chat_username == "somechannel"
    assert post.source_message_id == 12345
    assert post.source_url == "https://t.me/somechannel/12345"
    assert post.source_date == datetime.fromtimestamp(
        1788799200,
        tz=timezone.utc,
    )
    assert post.text == "Forwarded text"
    assert post.photo_count == 0


def test_channel_forward_without_username() -> None:
    message = Message.model_validate(
        _message_payload(channel_username=None)
    )

    post = parse_forwarded_post(message)

    assert post is not None
    assert post.source_chat_username is None
    assert post.source_url is None


def test_single_photo_is_counted_once() -> None:
    payload = _message_payload()
    payload.pop("text")
    payload["caption"] = "Photo caption"
    payload["photo"] = [
        {
            "file_id": "small",
            "file_unique_id": "same",
            "width": 320,
            "height": 240,
        },
        {
            "file_id": "large",
            "file_unique_id": "same",
            "width": 800,
            "height": 600,
        },
    ]

    post = parse_forwarded_post(Message.model_validate(payload))

    assert post is not None
    assert post.photo_count == 1
    assert post.text == "Photo caption"
    assert post.caption == "Photo caption"


def test_regular_message_returns_none() -> None:
    message = Message.model_validate(_message_payload(forwarded=False))

    assert parse_forwarded_post(message) is None
