"""Convert forwarded Telegram messages into application data."""

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
    has_photo: bool
    is_channel_post: bool


def parse_forwarded_post(message: Message) -> ForwardedPost | None:
    """Return accessible forward metadata without performing any I/O."""
    origin = message.forward_origin
    if origin is None:
        return None

    source_chat_id = None
    source_chat_title = None
    source_chat_username = None
    source_message_id = None
    source_url = None
    is_channel_post = isinstance(origin, MessageOriginChannel)

    if is_channel_post:
        source_chat_id = origin.chat.id
        source_chat_title = origin.chat.title
        source_chat_username = origin.chat.username
        source_message_id = origin.message_id
        if source_chat_username:
            source_url = (
                f"https://t.me/{source_chat_username}/{source_message_id}"
            )

    return ForwardedPost(
        source_chat_id=source_chat_id,
        source_chat_title=source_chat_title,
        source_chat_username=source_chat_username,
        source_message_id=source_message_id,
        source_date=origin.date,
        source_url=source_url,
        text=message.text,
        caption=message.caption,
        media_group_id=message.media_group_id,
        has_photo=bool(message.photo),
        is_channel_post=is_channel_post,
    )
