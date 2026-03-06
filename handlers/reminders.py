"""Handler /remind — пользовательские ежедневные напоминания."""
import html
import logging
import re

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from database.crud import (
    create_custom_reminder,
    delete_custom_reminder,
    list_custom_reminders,
)
from keyboards.main_menu import home_button

logger = logging.getLogger(__name__)
router = Router()

_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


def _home_only_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[home_button()]])


def _is_valid_time(raw: str) -> bool:
    if not _TIME_RE.match(raw):
        return False
    hh, mm = raw.split(":")
    return 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59


def _format_list(items: list[dict]) -> str:
    if not items:
        return (
            "<b>Напоминания</b>\n\n"
            "Пока нет ни одного напоминания.\n"
            "Добавьте: <code>/remind add 20:30 Проверить дневник</code>"
        )

    lines = ["<b>Ваши напоминания</b>\n"]
    for item in items:
        rid = item["reminder_id"]
        when = html.escape(item["reminder_time"])
        text = html.escape(item["reminder_text"])
        lines.append(f"{rid}. <b>{when}</b> — {text}")

    lines.append("")
    lines.append("Удалить: <code>/remind del ID</code>")
    return "\n".join(lines)


@router.message(Command("remind"))
async def cmd_remind(message: Message):
    """Управление пользовательскими ежедневными напоминаниями."""
    text = (message.text or "").strip()
    parts = text.split(maxsplit=3)
    user_id = message.from_user.id

    if len(parts) == 1 or (len(parts) >= 2 and parts[1].lower() == "list"):
        reminders = await list_custom_reminders(user_id)
        await message.answer(_format_list(reminders), parse_mode="HTML", reply_markup=_home_only_keyboard())
        return

    action = parts[1].lower()

    if action == "add":
        if len(parts) < 4:
            await message.answer(
                "Формат: <code>/remind add HH:MM Текст</code>\n"
                "Пример: <code>/remind add 20:30 Проверить дневник</code>",
                parse_mode="HTML",
                reply_markup=_home_only_keyboard(),
            )
            return

        raw_time = parts[2]
        reminder_text = parts[3].strip()

        if not _is_valid_time(raw_time):
            await message.answer(
                "Некорректное время. Используйте формат <code>HH:MM</code> (например, 08:15).",
                parse_mode="HTML",
                reply_markup=_home_only_keyboard(),
            )
            return

        if not reminder_text:
            await message.answer(
                "Текст напоминания не может быть пустым.",
                reply_markup=_home_only_keyboard(),
            )
            return

        if len(reminder_text) > 300:
            await message.answer(
                "Слишком длинный текст. Максимум 300 символов.",
                reply_markup=_home_only_keyboard(),
            )
            return

        reminder_id = await create_custom_reminder(user_id, reminder_text, raw_time)
        logger.info("Custom reminder created user_id=%d reminder_id=%d", user_id, reminder_id)
        await message.answer(
            f"✅ Напоминание добавлено: <b>{html.escape(raw_time)}</b> — {html.escape(reminder_text)}\n"
            "Показать список: <code>/remind list</code>",
            parse_mode="HTML",
            reply_markup=_home_only_keyboard(),
        )
        return

    if action in ("del", "delete", "remove"):
        if len(parts) < 3 or not parts[2].isdigit():
            await message.answer(
                "Формат: <code>/remind del ID</code>\n"
                "Пример: <code>/remind del 3</code>",
                parse_mode="HTML",
                reply_markup=_home_only_keyboard(),
            )
            return

        reminder_id = int(parts[2])
        removed = await delete_custom_reminder(user_id, reminder_id)
        if not removed:
            await message.answer(
                f"Напоминание с ID {reminder_id} не найдено.",
                reply_markup=_home_only_keyboard(),
            )
            return

        logger.info("Custom reminder deleted user_id=%d reminder_id=%d", user_id, reminder_id)
        await message.answer(
            f"🗑️ Напоминание {reminder_id} удалено.",
            reply_markup=_home_only_keyboard(),
        )
        return

    await message.answer(
        "<b>/remind — управление напоминаниями</b>\n\n"
        "<code>/remind list</code> — список\n"
        "<code>/remind add HH:MM Текст</code> — добавить\n"
        "<code>/remind del ID</code> — удалить",
        parse_mode="HTML",
        reply_markup=_home_only_keyboard(),
    )
