"""Convert forwarded Telegram messages into application data."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from aiogram.types import Message, MessageOriginChannel


@dataclass(frozen=True, slots=True)
class ForwardedPost:
    """Metadata available on a message forwarded to the bot."""

    source_chat_id: int | None
    source_chat_title: str | None
    source_chat_username: str | None
    source_message_id: int | None
    source_date: datetime | None
    source_url: str | None
    text: str | None
    caption: str | None
    media_group_id: str | None
    photo_count: int
    is_channel_post: bool


def parse_forwarded_post(message: Message) -> ForwardedPost | None:
    """Return accessible forward metadata without performing any I/O."""
    return parse_forwarded_messages((message,))


def parse_forwarded_messages(
    messages: Sequence[Message],
) -> ForwardedPost | None:
    """Combine ordered Telegram messages into one forwarded post."""
    ordered_messages = sorted(messages, key=lambda item: item.message_id)
    origins = [
        message.forward_origin
        for message in ordered_messages
        if message.forward_origin is not None
    ]
    if not origins:
        return None

    channel_origin = next(
        (
            origin
            for origin in origins
            if isinstance(origin, MessageOriginChannel)
        ),
        None,
    )
    origin = channel_origin or origins[0]

    source_chat_id = None
    source_chat_title = None
    source_chat_username = None
    source_message_id = None
    source_url = None
    is_channel_post = channel_origin is not None

    if is_channel_post:
        source_chat_id = channel_origin.chat.id
        source_chat_title = channel_origin.chat.title
        source_chat_username = channel_origin.chat.username
        source_message_id = channel_origin.message_id
        if source_chat_username:
            source_url = (
                f"https://t.me/{source_chat_username}/{source_message_id}"
            )

    content = next(
        (
            message.text or message.caption
            for message in ordered_messages
            if message.text or message.caption
        ),
        None,
    )
    caption = next(
        (
            message.caption
            for message in ordered_messages
            if message.caption
        ),
        None,
    )
    media_group_id = next(
        (
            message.media_group_id
            for message in ordered_messages
            if message.media_group_id is not None
        ),
        None,
    )

    return ForwardedPost(
        source_chat_id=source_chat_id,
        source_chat_title=source_chat_title,
        source_chat_username=source_chat_username,
        source_message_id=source_message_id,
        source_date=origin.date,
        source_url=source_url,
        text=content,
        caption=caption,
        media_group_id=media_group_id,
        photo_count=sum(bool(message.photo) for message in ordered_messages),
        is_channel_post=is_channel_post,
    )
