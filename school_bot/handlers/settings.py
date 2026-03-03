"""Handler /settings — настройка уведомлений."""
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database.crud import (
    get_notification_settings,
    toggle_notification,
    create_default_notifications,
    get_user_role,
)
from keyboards.main_menu import home_button

logger = logging.getLogger(__name__)
router = Router()


def _settings_keyboard(settings_list: list, role: str) -> InlineKeyboardMarkup:
    """Построить клавиатуру настроек уведомлений."""
    type_labels = {
        "grades": "Оценки",
        "homework": "Домашние задания",
    }

    buttons = []
    for s in settings_list:
        ntype = s["notification_type"]

        # Студенты не видят оценки
        if ntype == "grades" and role == "student":
            continue

        enabled = s["is_enabled"]
        label = type_labels.get(ntype, ntype)
        icon = "\U0001f514" if enabled else "\U0001f515"
        status = "ON" if enabled else "OFF"

        text = f"{icon} {label}: {status}"
        callback = f"settings:toggle:{ntype}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=callback)])

    buttons.append([home_button()])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _show_settings(user_id: int, role: str, edit_message=None, send_message=None):
    """Получить настройки и показать меню."""
    notif_settings = await get_notification_settings(user_id)

    if not notif_settings:
        await create_default_notifications(user_id, None)
        notif_settings = await get_notification_settings(user_id)

    text = (
        "<b>Настройки уведомлений</b>\n\n"
        "Нажмите на кнопку, чтобы включить или выключить.\n\n"
        "\U0001f514 Оценки — ежедневно в 18:00\n"
        "\U0001f514 ДЗ — ежедневно в 19:00"
    )

    keyboard = _settings_keyboard(notif_settings, role)

    if edit_message:
        await edit_message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    elif send_message:
        await send_message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Команда /settings — показать настройки уведомлений."""
    role = await get_user_role(message.from_user.id) or "student"
    await _show_settings(message.from_user.id, role, send_message=message)


@router.callback_query(F.data == "menu:settings")
async def cb_menu_settings(callback: CallbackQuery):
    """Кнопка 'Настройки' из главного меню."""
    await callback.answer()
    role = await get_user_role(callback.from_user.id) or "student"
    await _show_settings(callback.from_user.id, role, edit_message=callback.message)


@router.callback_query(F.data.startswith("settings:toggle:"))
async def cb_toggle_notification(callback: CallbackQuery):
    """Переключить уведомление вкл/выкл."""
    await callback.answer()
    user_id = callback.from_user.id

    parts = callback.data.split(":")
    if len(parts) != 3:
        return

    notification_type = parts[2]
    if notification_type not in ("grades", "homework"):
        return

    # Получаем текущее состояние и переключаем
    notif_settings = await get_notification_settings(user_id)
    current = next(
        (s for s in notif_settings if s["notification_type"] == notification_type),
        None,
    )

    if current is None:
        return

    new_state = not current["is_enabled"]
    await toggle_notification(user_id, notification_type, new_state)

    # Показать обновлённое меню
    role = await get_user_role(user_id) or "student"
    await _show_settings(user_id, role, edit_message=callback.message)
