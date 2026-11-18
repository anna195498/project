"""Application entry point for Geo Messenger."""

import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import get_settings
from db.database import initialize_database
from handlers.location import router as location_router
from handlers.rules import router as rules_router
from handlers.start import router as start_router
from services.location_provider import TelegramLiveLocationProvider


async def main() -> None:
    """Initialize storage and start the Telegram bot."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    await initialize_database(settings.database_path)

    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher()
    dispatcher["location_provider"] = TelegramLiveLocationProvider()
    dispatcher.include_routers(start_router, rules_router, location_router)

    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
