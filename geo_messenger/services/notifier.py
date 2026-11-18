"""Telegram notification delivery."""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError

logger = logging.getLogger(__name__)


async def send_notification(
    bot: Bot,
    contact_telegram_id: int,
    owner_name: str,
    text: str,
    owner_telegram_id: int | None = None,
) -> None:
    """Send a notification and inform the owner if delivery is forbidden."""
    notification = f"От имени {owner_name}: {text}"
    try:
        await bot.send_message(contact_telegram_id, notification)
    except TelegramForbiddenError:
        logger.warning(
            "Cannot message contact %s; they may not have started the bot",
            contact_telegram_id,
        )
        if owner_telegram_id is not None:
            try:
                await bot.send_message(
                    owner_telegram_id,
                    "Не удалось отправить уведомление контакту. "
                    "Попросите его открыть бота и нажать Start.",
                )
            except TelegramAPIError:
                logger.exception(
                    "Could not notify owner %s about failed delivery",
                    owner_telegram_id,
                )
    except TelegramAPIError:
        logger.exception("Telegram API failed to send a notification")
        raise
