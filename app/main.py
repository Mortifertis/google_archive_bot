"""Application entry point."""

import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import load_config
from app.handlers import create_router


async def main() -> None:
    """Configure and start long polling."""
    config = load_config()
    bot = Bot(token=config.bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(config.owner_user_id))

    try:
        logging.info("Bot started")
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        logging.info("Bot stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
