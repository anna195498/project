"""Telegram notification delivery."""

import logging

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
)
from db.repository import consume_rate_limit

logger = logging.getLogger(__name__)
_MESSAGE_LIMIT = 10
_MESSAGE_WINDOW_SECONDS = 60


async def _allow_notification(owner_telegram_id: int) -> bool:
    """Allow at most ten outgoing notifications per owner per minute."""
    return await consume_rate_limit(
        owner_telegram_id,
        "notification",
        _MESSAGE_LIMIT,
        _MESSAGE_WINDOW_SECONDS,
    )


async def send_notification(
    bot: Bot,
    contact_telegram_id: int,
    owner_name: str,
    text: str,
    owner_telegram_id: int | None = None,
) -> None:
    """Send a notification and inform the owner if delivery is forbidden."""
    if owner_telegram_id is not None:
        if not await _allow_notification(owner_telegram_id):
            logger.warning("Notification rate limit reached")
            return

    notification = f"От имени {owner_name}: {text}"
    try:
        await bot.send_message(contact_telegram_id, notification)
    except (TelegramForbiddenError, TelegramBadRequest) as error:
        logger.warning(
            "Telegram rejected notification delivery (%s)",
            type(error).__name__,
        )
        if owner_telegram_id is not None:
            try:
                await bot.send_message(
                    owner_telegram_id,
                    "Не удалось отправить уведомление контакту. "
                    "Попросите его открыть бота и нажать Start.",
                )
            except TelegramAPIError as owner_error:
                logger.error(
                    "Could not notify owner about failed delivery (%s)",
                    type(owner_error).__name__,
                )
    except TelegramAPIError as error:
        logger.error(
            "Telegram API failed to send a notification (%s)",
            type(error).__name__,
        )
        raise
