"""Handler /profile — профиль пользователя."""
import html
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup

from database.crud import get_user, get_user_role, get_user_children
from keyboards.main_menu import home_button

logger = logging.getLogger(__name__)
router = Router()

_home_kb = InlineKeyboardMarkup(inline_keyboard=[[home_button()]])

_ROLE_LABELS = {
    "admin": "Администратор",
    "parent": "Родитель",
    "student": "Ученик",
}


def _mask_login(login: str) -> str:
    """Маскирует логин: 'user@example.com' → 'us***@example.com'."""
    if not login:
        return "—"
    if "@" in login:
        local, domain = login.split("@", 1)
        masked = local[:2] + "***" if len(local) > 2 else "***"
        return f"{masked}@{domain}"
    return login[:2] + "***" if len(login) > 2 else "***"


async def _show_profile(user_id: int, message):
    """Общая логика показа профиля (для команды и кнопки меню)."""
    user = await get_user(user_id)
    if not user:
        await message.answer(
            "Профиль не найден. Нажмите /start для регистрации.",
            reply_markup=_home_kb,
        )
        return

    role = user.get("role") or await get_user_role(user_id) or "—"
    role_label = _ROLE_LABELS.get(role, role)

    first_name = html.escape(user.get("first_name") or "—")
    last_name = html.escape(user.get("last_name") or "")
    username = user.get("username")
    username_str = f"@{html.escape(username)}" if username else "не задан"
    registered_at = (user.get("registered_at") or "—")[:10]

    mesh_login = user.get("mesh_login")
    mesh_login_str = _mask_login(mesh_login) if mesh_login else "не привязан"

    lines = [
        "<b>Мой профиль</b>\n",
        f"Имя: {first_name} {last_name}".strip(),
        f"Username: {username_str}",
        f"ID: <code>{user_id}</code>",
        f"Роль: {role_label}",
        f"Зарегистрирован: {registered_at}",
        f"Логин МЭШ: {html.escape(mesh_login_str)}",
    ]

    children = await get_user_children(user_id)
    if children:
        lines.append(f"\n<b>Дети ({len(children)}):</b>")
        for child in children:
            child_name = html.escape(
                f"{child['first_name']} {child['last_name']}"
            )
            class_name = html.escape(child.get("class_name") or "")
            child_str = f"  • {child_name}"
            if class_name:
                child_str += f", {class_name}"
            lines.append(child_str)
    else:
        lines.append("\nДети: не привязаны")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=_home_kb)


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    """Команда /profile — показать профиль."""
    await _show_profile(message.from_user.id, message)


@router.callback_query(F.data == "menu:profile")
async def cb_menu_profile(callback: CallbackQuery):
    """Кнопка 'Профиль' из главного меню."""
    await callback.answer()
    await _show_profile(callback.from_user.id, callback.message)
