"""Telegram message handlers."""

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.media_group import MediaGroupCollector
from app.telegram_parser import (ForwardedPost, parse_forwarded_messages,
                                 parse_forwarded_post)

logger = logging.getLogger(__name__)

START_MESSAGE = (
    "Telegram Archive Bot работает.\n\n"
    "Перешли сюда пост из Telegram-канала. На следующих этапах бот будет "
    "сохранять такие сообщения в Google Drive."
)
RECEIVED_MESSAGE = (
    "Сообщение получено.\n"
    "Для архивации перешли пост из Telegram-канала."
)
PRIVATE_MESSAGE = "Этот бот является приватным."
UNSUPPORTED_FORWARD_MESSAGE = (
    "Пересланное сообщение получено, но сейчас поддерживаются только "
    "публикации из Telegram-каналов."
)
UNSUPPORTED_ALBUM_MESSAGE = (
    "Получен альбом, но сейчас поддерживаются только пересланные "
    "публикации из Telegram-каналов."
)


def _format_forwarded_post(post: ForwardedPost) -> str:
    """Build a short diagnostic response for a forwarded channel post."""
    username = (
        f"@{post.source_chat_username}"
        if post.source_chat_username
        else "недоступен"
    )
    source_date = (
        post.source_date.strftime("%d.%m.%Y %H:%M")
        if post.source_date
        else "недоступна"
    )
    has_text = bool(post.text or post.caption)

    return "\n".join(
        (
            "Пересланный пост распознан.",
            "",
            f"Канал: {post.source_chat_title or 'недоступен'}",
            f"Username: {username}",
            f"Message ID: {post.source_message_id}",
            f"Дата: {source_date}",
            f"Ссылка: {post.source_url or 'недоступна'}",
            f"Текст: {'есть' if has_text else 'нет'}",
            f"Фото: {post.photo_count}",
            f"Media group: {post.media_group_id or 'нет'}",
        )
    )


def create_router(
    owner_user_id: int,
    media_group_collector: MediaGroupCollector,
) -> Router:
    """Create a router whose private handlers belong to one Telegram user."""
    router = Router()

    @router.message(CommandStart(), F.from_user.id == owner_user_id)
    async def handle_start(message: Message) -> None:
        await message.answer(START_MESSAGE)

    @router.message(F.from_user.id != owner_user_id)
    async def handle_non_owner(message: Message) -> None:
        await message.answer(PRIVATE_MESSAGE)

    @router.message(F.from_user.id == owner_user_id, F.media_group_id)
    async def handle_media_group(message: Message) -> None:
        async def process_album(messages: list[Message]) -> None:
            photo_count = sum(bool(item.photo) for item in messages)
            logger.info(
                "Telegram media group collected: media_group_id=%s, "
                "items=%s, photos=%s",
                messages[0].media_group_id,
                len(messages),
                photo_count,
            )
            post = parse_forwarded_messages(messages)
            if post is None or not post.is_channel_post:
                await messages[0].answer(UNSUPPORTED_ALBUM_MESSAGE)
                return
            await messages[0].answer(_format_forwarded_post(post))

        await media_group_collector.add(message, process_album)

    @router.message(F.from_user.id == owner_user_id, F.forward_origin)
    async def handle_forwarded_message(message: Message) -> None:
        post = parse_forwarded_post(message)
        if post is None or not post.is_channel_post:
            await message.answer(UNSUPPORTED_FORWARD_MESSAGE)
            return

        logger.info(
            "Forwarded channel post detected: chat_id=%s, message_id=%s, "
            "media_group_id=%s",
            post.source_chat_id,
            post.source_message_id,
            post.media_group_id,
        )
        await message.answer(_format_forwarded_post(post))

    @router.message(F.from_user.id == owner_user_id)
    async def handle_owner_message(message: Message) -> None:
        await message.answer(RECEIVED_MESSAGE)

    return router
