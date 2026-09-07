"""Telegram message handlers."""

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

START_MESSAGE = (
    "Telegram Archive Bot работает.\n\n"
    "Перешли сюда пост из Telegram-канала. На следующих этапах бот будет "
    "сохранять такие сообщения в Google Drive."
)
RECEIVED_MESSAGE = (
    "Сообщение получено.\n"
    "На следующем этапе добавим обработку пересланных Telegram-постов."
)
PRIVATE_MESSAGE = "Этот бот является приватным."


def create_router(owner_user_id: int) -> Router:
    """Create a router whose private handlers belong to one Telegram user."""
    router = Router()

    @router.message(CommandStart(), F.from_user.id == owner_user_id)
    async def handle_start(message: Message) -> None:
        await message.answer(START_MESSAGE)

    @router.message(F.from_user.id != owner_user_id)
    async def handle_non_owner(message: Message) -> None:
        await message.answer(PRIVATE_MESSAGE)

    @router.message(F.from_user.id == owner_user_id)
    async def handle_owner_message(message: Message) -> None:
        await message.answer(RECEIVED_MESSAGE)

    return router
