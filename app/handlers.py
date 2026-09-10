"""Telegram message handlers."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import GoogleConfig
from app.document_builder import DocumentImageError
from app.google_drive import (DriveDocument, GoogleAuthError,
                              archive_forwarded_post,
                              find_existing_archived_post)
from app.media_group import MediaGroupCollector, is_supported_media_group
from app.telegram_media import (DownloadedMedia, TelegramMediaError,
                                download_message_media)
from app.telegram_parser import (ForwardedPost, parse_forwarded_messages,
                                 parse_forwarded_post)

logger = logging.getLogger(__name__)

START_MESSAGE = (
    "Telegram Archive Bot работает.\n\n"
    "Перешли сюда пост из Telegram-канала — я сохраню "
    "его в Google Drive как Google Doc.\n\n"
    "Поддерживаются текст, фотографии, видео, GIF/анимации, "
    "фотоальбомы и смешанные фото/видео альбомы."
)
RECEIVED_MESSAGE = (
    "Сообщение получено.\n" "Для архивации перешли пост из Telegram-канала."
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
MIXED_ALBUM_MESSAGE = "Альбом содержит неподдерживаемый тип медиа."
PHOTO_DOWNLOAD_ERROR_MESSAGE = (
    "❌ Не удалось скачать изображение из публикации.\n\n"
    "Попробуй переслать публикацию ещё раз."
)
ALBUM_DOWNLOAD_ERROR_MESSAGE = (
    "❌ Не удалось скачать одно из изображений альбома.\n\n"
    "Попробуй переслать публикацию ещё раз."
)
IMAGE_SAVE_ERROR_MESSAGE = (
    "❌ Не удалось сохранить изображение из публикации.\n\n"
    "Подробности записаны в журнал."
)
GOOGLE_AUTH_MESSAGE = (
    "❌ Google Drive не настроен.\n\n"
    "Выполни на компьютере:\n"
    "python -m app.google_auth\n\n"
    "и затем повтори отправку поста."
)
GOOGLE_ERROR_MESSAGE = (
    "❌ Не удалось сохранить пост в Google Drive.\n\n"
    "Подробности записаны в журнал."
)

MediaDownloader = Callable[[], Awaitable[Sequence[DownloadedMedia]]]


async def _archive_with_deduplication(
    post: ForwardedPost,
    google_config: GoogleConfig,
    archive_lock: asyncio.Lock,
    download_media: MediaDownloader,
) -> tuple[DriveDocument, bool, Sequence[DownloadedMedia]]:
    """Serialize lookup, media download, and upload for one post."""
    async with archive_lock:
        existing = await asyncio.to_thread(
            find_existing_archived_post,
            post,
            google_config,
        )
        if existing is not None:
            return existing, True, ()

        media = await download_media()
        document = await asyncio.to_thread(
            archive_forwarded_post,
            post,
            google_config,
            media,
        )
        return document, False, media


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
            f"Видео: {post.video_count}",
            f"Анимации: {post.animation_count}",
            f"Media group: {post.media_group_id or 'нет'}",
        )
    )


def _document_keyboard(web_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть Google Doc",
                    url=web_url,
                )
            ]
        ]
    )


def _format_media_statistics(
    post: ForwardedPost,
    media: Sequence[DownloadedMedia],
) -> str:
    """Build non-empty media counters and graceful-limit diagnostics."""
    lines = []
    if post.photo_count:
        lines.append(f"🖼 Фото: {post.photo_count}")
    if post.video_count:
        lines.append(f"🎬 Видео: {post.video_count}")
    if post.animation_count:
        lines.append(f"🎞 Анимации: {post.animation_count}")
    unavailable = sum(bool(item.unavailable_reason) for item in media)
    if unavailable:
        lines.append(
            f"⚠️ {unavailable} медиафайл не архивирован из-за лимита "
            "Telegram."
        )
    return "\n" + "\n".join(lines) if lines else ""


def create_router(
    owner_user_id: int,
    media_group_collector: MediaGroupCollector,
    google_config: GoogleConfig,
) -> Router:
    """Create a router whose private handlers belong to one Telegram user."""
    router = Router()
    archive_lock = asyncio.Lock()

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
            if not is_supported_media_group(messages):
                await messages[0].answer(MIXED_ALBUM_MESSAGE)
                return

            status = await messages[0].answer(
                f"⏳ Сохраняю альбом из {len(messages)} медиафайлов…"
            )
            async def download_media() -> Sequence[DownloadedMedia]:
                media: list[DownloadedMedia] = []
                for item in messages:
                    media.append(
                        await download_message_media(item.bot, item)
                    )
                return media

            try:
                document, duplicate, media = (
                    await _archive_with_deduplication(
                        post,
                        google_config,
                        archive_lock,
                        download_media,
                    )
                )
            except TelegramMediaError:
                logger.exception("Could not download Telegram photo album")
                await status.edit_text(ALBUM_DOWNLOAD_ERROR_MESSAGE)
                return
            except GoogleAuthError:
                await status.edit_text(GOOGLE_AUTH_MESSAGE)
                return
            except DocumentImageError:
                logger.exception("Could not add album image to DOCX")
                await status.edit_text(IMAGE_SAVE_ERROR_MESSAGE)
                return
            except Exception:
                logger.exception("Could not archive Telegram photo album")
                await status.edit_text(GOOGLE_ERROR_MESSAGE)
                return

            if duplicate:
                await status.edit_text(
                    "♻️ Уже сохранено\n\n" f"📄 {document.name}",
                    reply_markup=_document_keyboard(document.web_url),
                )
                return

            logger.info(
                "Telegram photo album archived: media_group_id=%s, "
                "photos=%s",
                post.media_group_id,
                post.photo_count,
            )
            channel_title = post.source_chat_title or "недоступен"
            await status.edit_text(
                "✅ Сохранено\n\n"
                f"📄 {document.name}\n"
                f"📢 {channel_title}\n"
                + _format_media_statistics(post, media),
                reply_markup=_document_keyboard(document.web_url),
            )

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
        if not post.media_count and (
            message.content_type != "text" or not post.text
        ):
            await message.answer(_format_forwarded_post(post))
            return

        async def download_media() -> Sequence[DownloadedMedia]:
            if not post.media_count:
                return ()
            return (await download_message_media(message.bot, message),)

        if post.photo_count:
            status = await message.answer("⏳ Проверяю Google Drive…")
        else:
            status = await message.answer("⏳ Сохраняю в Google Drive…")
        try:
            document, duplicate, media = await _archive_with_deduplication(
                post,
                google_config,
                archive_lock,
                download_media,
            )
        except TelegramMediaError:
            logger.exception("Could not download Telegram post photo")
            await status.edit_text(PHOTO_DOWNLOAD_ERROR_MESSAGE)
            return
        except GoogleAuthError:
            await status.edit_text(GOOGLE_AUTH_MESSAGE)
            return
        except DocumentImageError:
            logger.exception("Could not add post image to DOCX")
            await status.edit_text(IMAGE_SAVE_ERROR_MESSAGE)
            return
        except Exception:
            logger.exception("Could not archive forwarded Telegram post")
            await status.edit_text(GOOGLE_ERROR_MESSAGE)
            return

        if duplicate:
            await status.edit_text(
                "♻️ Уже сохранено\n\n" f"📄 {document.name}",
                reply_markup=_document_keyboard(document.web_url),
            )
            return

        channel_title = post.source_chat_title or "недоступен"
        logger.info(
            "Forwarded Telegram post archived: message_id=%s, photos=%s",
            post.source_message_id,
            post.photo_count,
        )
        await status.edit_text(
            "✅ Сохранено\n\n"
            f"📄 {document.name}\n"
            f"📢 {channel_title}"
            + _format_media_statistics(post, media),
            reply_markup=_document_keyboard(document.web_url),
        )

    @router.message(F.from_user.id == owner_user_id)
    async def handle_owner_message(message: Message) -> None:
        await message.answer(RECEIVED_MESSAGE)

    return router
