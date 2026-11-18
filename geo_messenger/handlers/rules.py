"""FSM-based location notification rule creation."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from db.repository import consume_rate_limit, create_rule, get_contacts

logger = logging.getLogger(__name__)
router = Router(name="rules")
_RULE_LIMIT = 5
_RULE_WINDOW_SECONDS = 60 * 60


async def _allow_rule_creation(user_id: int) -> bool:
    """Allow at most five rule-creation attempts per user per hour."""
    return await consume_rate_limit(
        user_id, "rule_create", _RULE_LIMIT, _RULE_WINDOW_SECONDS
    )


class RuleCreation(StatesGroup):
    """States for creating a location rule."""

    waiting_for_location = State()
    waiting_for_radius = State()
    waiting_for_contact = State()
    waiting_for_text = State()
    waiting_for_confirmation = State()


@router.message(Command("rule"))
async def begin_rule_creation(message: Message, state: FSMContext) -> None:
    """Start the rule creation flow."""
    if message.from_user is None:
        return
    if not await _allow_rule_creation(message.from_user.id):
        await message.answer(
            "Достигнут лимит создания правил (5 в час). Попробуйте позже."
        )
        return
    await state.clear()
    await state.set_state(RuleCreation.waiting_for_location)
    await message.answer(
        "Отправьте геопозицию точки назначения через скрепку → Геопозиция."
    )


@router.message(RuleCreation.waiting_for_location, F.location)
async def receive_rule_location(message: Message, state: FSMContext) -> None:
    """Save rule coordinates and request its radius."""
    if message.location is None:
        return
    await state.update_data(
        latitude=message.location.latitude,
        longitude=message.location.longitude,
    )
    await state.set_state(RuleCreation.waiting_for_radius)
    await message.answer("Введите радиус срабатывания в метрах (например, 100).")


@router.message(RuleCreation.waiting_for_location)
async def prompt_for_location(message: Message) -> None:
    """Prompt for a location when another message was sent."""
    await message.answer("Нужна геопозиция, отправленная через скрепку → Геопозиция.")


@router.message(RuleCreation.waiting_for_radius)
async def receive_rule_radius(message: Message, state: FSMContext) -> None:
    """Validate and save the rule radius."""
    try:
        radius_m = int((message.text or "").strip())
    except ValueError:
        await message.answer("Введите целое число метров, например 100.")
        return
    if not 1 <= radius_m <= 100_000:
        await message.answer("Радиус должен быть от 1 до 100000 метров.")
        return
    await state.update_data(radius_m=radius_m)

    if message.from_user is None:
        return
    contacts = await get_contacts(message.from_user.id)
    if not contacts:
        await message.answer(
            "Контактов пока нет. Отправьте приглашение через /start, "
            "а затем создайте правило заново командой /rule."
        )
        await state.clear()
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=contact.contact_name,
                    callback_data=f"rule_contact:{contact.id}",
                )
            ]
            for contact in contacts
        ]
    )
    await state.set_state(RuleCreation.waiting_for_contact)
    await message.answer("Выберите контакт для уведомления:", reply_markup=keyboard)


@router.callback_query(
    RuleCreation.waiting_for_contact, F.data.startswith("rule_contact:")
)
async def select_rule_contact(callback: CallbackQuery, state: FSMContext) -> None:
    """Store the selected contact and request the notification text."""
    if callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    try:
        contact_id = int(callback.data.partition(":")[2])
    except ValueError:
        await callback.answer("Некорректный контакт.", show_alert=True)
        return

    contacts = await get_contacts(callback.from_user.id)
    contact = next((item for item in contacts if item.id == contact_id), None)
    if contact is None:
        await callback.answer("Контакт не найден.", show_alert=True)
        return

    await state.update_data(
        contact_id=contact.id,
        contact_name=contact.contact_name,
    )
    await state.set_state(RuleCreation.waiting_for_text)
    await callback.answer()
    if callback.message:
        await callback.bot.send_message(
            callback.message.chat.id, "Введите текст сообщения контакту."
        )


@router.message(RuleCreation.waiting_for_text)
async def receive_rule_text(message: Message, state: FSMContext) -> None:
    """Save message text and show a confirmation summary."""
    text = (message.text or "").strip()
    if not text:
        await message.answer("Сообщение должно содержать текст. Введите его ещё раз.")
        return
    if len(text) > 500:
        await message.answer("Текст слишком длинный (максимум 500 символов).")
        return
    await state.update_data(message_text=text)
    data = await state.get_data()
    latitude = float(data["latitude"])
    longitude = float(data["longitude"])
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Создать", callback_data="rule_confirm"),
                InlineKeyboardButton(text="Отмена", callback_data="rule_cancel"),
            ]
        ]
    )
    await state.set_state(RuleCreation.waiting_for_confirmation)
    await message.answer(
        "Проверьте правило:\n"
        f"Точка: {latitude:.6f}, {longitude:.6f}\n"
        f"Радиус: {data['radius_m']} м\n"
        f"Контакт: {data['contact_name']}\n"
        f"Сообщение: {text}\n\nСоздать правило?",
        reply_markup=keyboard,
    )


@router.callback_query(RuleCreation.waiting_for_confirmation, F.data == "rule_confirm")
async def confirm_rule_creation(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Persist a confirmed rule and finish the FSM."""
    data = await state.get_data()
    try:
        rule_id = await create_rule(
            owner_id=callback.from_user.id,
            contact_id=int(data["contact_id"]),
            lat=float(data["latitude"]),
            lon=float(data["longitude"]),
            radius_m=int(data["radius_m"]),
            text=str(data["message_text"]),
        )
    except ValueError:
        logger.warning("Rule creation failed: contact is no longer available")
        await callback.answer("Контакт больше недоступен.", show_alert=True)
        await state.clear()
        return
    await state.clear()
    await callback.answer("Правило создано")
    if callback.message:
        await callback.bot.send_message(
            callback.message.chat.id, f"Правило №{rule_id} сохранено."
        )


@router.callback_query(RuleCreation.waiting_for_confirmation, F.data == "rule_cancel")
async def cancel_rule_creation(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel rule creation and clear FSM data."""
    await state.clear()
    await callback.answer("Создание отменено")
    if callback.message:
        await callback.bot.send_message(
            callback.message.chat.id, "Создание правила отменено."
        )


# TODO: Add several contacts per rule.
# TODO: Add rule listing and deletion controls.
# TODO: Add time-of-day and weekday restrictions.
# TODO: Support resetting is_inside when the owner leaves the point.
