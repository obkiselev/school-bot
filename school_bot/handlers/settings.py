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
    get_user_theme,
    set_user_theme,
)
from keyboards.main_menu import home_button
from services.gamification import THEMES

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

    buttons.append([InlineKeyboardButton(
        text="\U0001f3a8 \u0422\u0435\u043c\u0430 \u043e\u0444\u043e\u0440\u043c\u043b\u0435\u043d\u0438\u044f",
        callback_data="settings:theme",
    )])
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


# ============================================================================
# THEME SELECTION
# ============================================================================

def _theme_keyboard(current_theme: str) -> InlineKeyboardMarkup:
    """Build theme selection keyboard."""
    buttons = []
    for key, theme in THEMES.items():
        check = "\u2705 " if key == current_theme else ""
        buttons.append([InlineKeyboardButton(
            text=f"{check}{theme['display_name']}",
            callback_data=f"theme:{key}",
        )])
    buttons.append([InlineKeyboardButton(
        text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434 \u043a \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430\u043c",
        callback_data="menu:settings",
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "settings:theme")
async def cb_choose_theme(callback: CallbackQuery):
    """Show theme selection menu."""
    await callback.answer()
    user_id = callback.from_user.id
    current = await get_user_theme(user_id)
    current_name = THEMES.get(current, THEMES["neutral"])["display_name"]

    await callback.message.edit_text(
        f"\U0001f3a8 <b>\u0412\u044b\u0431\u0435\u0440\u0438 \u0442\u0435\u043c\u0443 \u043e\u0444\u043e\u0440\u043c\u043b\u0435\u043d\u0438\u044f</b>\n\n"
        f"\u0422\u0435\u043a\u0443\u0449\u0430\u044f: {current_name}\n\n"
        f"\u0422\u0435\u043c\u0430 \u043c\u0435\u043d\u044f\u0435\u0442 \u0441\u0442\u0438\u043b\u044c \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0439 \u0432 \u0442\u0435\u0441\u0442\u0430\u0445:\n"
        f"\u043d\u0430\u0437\u0432\u0430\u043d\u0438\u044f \u0443\u0440\u043e\u0432\u043d\u0435\u0439, XP, \u0434\u043e\u0441\u0442\u0438\u0436\u0435\u043d\u0438\u044f \u0438 \u0440\u0435\u0430\u043a\u0446\u0438\u0438.",
        reply_markup=_theme_keyboard(current),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("theme:"))
async def cb_set_theme(callback: CallbackQuery):
    """Set user's gamification theme."""
    theme_key = callback.data.split(":", 1)[1]
    if theme_key not in THEMES:
        await callback.answer("\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u0430\u044f \u0442\u0435\u043c\u0430")
        return

    user_id = callback.from_user.id
    await set_user_theme(user_id, theme_key)
    await callback.answer(f"\u0422\u0435\u043c\u0430: {THEMES[theme_key]['display_name']}")

    # Refresh theme menu
    await callback.message.edit_text(
        f"\U0001f3a8 <b>\u0412\u044b\u0431\u0435\u0440\u0438 \u0442\u0435\u043c\u0443 \u043e\u0444\u043e\u0440\u043c\u043b\u0435\u043d\u0438\u044f</b>\n\n"
        f"\u0422\u0435\u043a\u0443\u0449\u0430\u044f: {THEMES[theme_key]['display_name']}\n\n"
        f"\u0422\u0435\u043c\u0430 \u043c\u0435\u043d\u044f\u0435\u0442 \u0441\u0442\u0438\u043b\u044c \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0439 \u0432 \u0442\u0435\u0441\u0442\u0430\u0445:\n"
        f"\u043d\u0430\u0437\u0432\u0430\u043d\u0438\u044f \u0443\u0440\u043e\u0432\u043d\u0435\u0439, XP, \u0434\u043e\u0441\u0442\u0438\u0436\u0435\u043d\u0438\u044f \u0438 \u0440\u0435\u0430\u043a\u0446\u0438\u0438.",
        reply_markup=_theme_keyboard(theme_key),
        parse_mode="HTML",
    )
