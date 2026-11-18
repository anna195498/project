"""Registration and contact invitation handlers."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from db.repository import add_contact, get_user_name, register_user

router = Router(name="start")


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    """Register a user and process an optional contact invitation."""
    if message.from_user is None:
        return

    user_id = message.from_user.id
    name = message.from_user.full_name
    await register_user(user_id, name)
    payload = (message.text or "").partition(" ")[2].strip()

    if payload.startswith("invite_"):
        try:
            owner_id = int(payload.removeprefix("invite_"))
        except ValueError:
            await message.answer("Ссылка-приглашение некорректна.")
            return
        owner_name = await get_user_name(owner_id)
        if owner_id == user_id or owner_name is None:
            await message.answer("Приглашение недействительно.")
            return
        await add_contact(owner_id, user_id, name)
        await message.answer(
            f"Вы добавлены в контакты пользователя {owner_name}. "
            "Теперь он может выбрать вас для уведомлений."
        )
        return

    me = await message.bot.get_me()
    invitation = f"https://t.me/{me.username}?start=invite_{user_id}"
    await message.answer(
        f"Привет, {name}! Я Geo Messenger. "
        "Создайте правило командой /rule.\n\n"
        "Чтобы добавить контакт, отправьте ему эту ссылку и попросите нажать Start:\n"
        f"{invitation}"
    )
