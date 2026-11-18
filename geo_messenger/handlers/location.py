"""Handlers for regular and live Telegram location updates."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from handlers.rules import RuleCreation
from services.geo import check_rules_for_location
from services.location_provider import TelegramLiveLocationProvider

router = Router(name="location")


async def process_location(
    message: Message, location_provider: TelegramLiveLocationProvider
) -> None:
    """Cache a received position and check the owner's active rules."""
    if message.from_user is None or message.location is None:
        return
    user_id = message.from_user.id
    latitude = message.location.latitude
    longitude = message.location.longitude
    await location_provider.update_location(user_id, latitude, longitude)
    await check_rules_for_location(user_id, latitude, longitude, message.bot)


@router.message(F.location)
async def handle_location(
    message: Message,
    state: FSMContext,
    location_provider: TelegramLiveLocationProvider,
) -> None:
    """Process an ordinary or live location message."""
    if await state.get_state() == RuleCreation.waiting_for_location.state:
        return
    await process_location(message, location_provider)


@router.edited_message(F.location)
async def handle_edited_live_location(
    message: Message,
    state: FSMContext,
    location_provider: TelegramLiveLocationProvider,
) -> None:
    """Process edited live-location updates as fresh location samples."""
    if await state.get_state() == RuleCreation.waiting_for_location.state:
        return
    await process_location(message, location_provider)
