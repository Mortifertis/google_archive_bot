"""In-memory collection of Telegram media group messages."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from aiogram.types import Message

MediaGroupCallback = Callable[[list[Message]], Awaitable[None]]

logger = logging.getLogger(__name__)


def is_photo_album(messages: list[Message]) -> bool:
    """Return whether every collected album item is a photo."""
    return bool(messages) and all(bool(message.photo) for message in messages)


def is_supported_media_group(messages: list[Message]) -> bool:
    """Return whether every item has exactly one supported media type."""
    return bool(messages) and all(
        sum(
            (
                bool(message.photo),
                message.video is not None,
                message.animation is not None,
            )
        )
        == 1
        for message in messages
    )


class MediaGroupCollector:
    """Collect album items and deliver each group after a quiet interval."""

    def __init__(self, debounce_seconds: float = 1.5) -> None:
        if debounce_seconds <= 0:
            raise ValueError("debounce_seconds must be greater than 0")
        self._debounce_seconds = debounce_seconds
        self._groups: dict[str, list[Message]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def add(
        self,
        message: Message,
        callback: MediaGroupCallback,
    ) -> None:
        """Add one album item and restart that album's debounce timer."""
        media_group_id = message.media_group_id
        if media_group_id is None:
            raise ValueError("message must have a media_group_id")

        async with self._lock:
            if self._closed:
                raise RuntimeError("media group collector is closed")
            self._groups.setdefault(media_group_id, []).append(message)
            previous_task = self._tasks.get(media_group_id)
            if previous_task is not None:
                previous_task.cancel()
            task = asyncio.create_task(
                self._deliver(media_group_id, callback),
                name=f"media-group-{media_group_id}",
            )
            self._tasks[media_group_id] = task

    async def _deliver(
        self,
        media_group_id: str,
        callback: MediaGroupCallback,
    ) -> None:
        try:
            await asyncio.sleep(self._debounce_seconds)
            current_task = asyncio.current_task()
            async with self._lock:
                if self._tasks.get(media_group_id) is not current_task:
                    return
                messages = sorted(
                    self._groups.pop(media_group_id),
                    key=lambda message: message.message_id,
                )
                self._tasks.pop(media_group_id, None)
            await callback(messages)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Failed to process Telegram media group: "
                "media_group_id=%s",
                media_group_id,
            )
            async with self._lock:
                self._groups.pop(media_group_id, None)
                if self._tasks.get(media_group_id) is asyncio.current_task():
                    self._tasks.pop(media_group_id, None)

    async def close(self) -> None:
        """Cancel pending deliveries and discard incomplete groups."""
        async with self._lock:
            self._closed = True
            tasks = list(self._tasks.values())
            self._tasks.clear()
            self._groups.clear()
            for task in tasks:
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
