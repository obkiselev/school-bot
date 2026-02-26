from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.config import QUESTION_COUNTS


def question_count_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for count in QUESTION_COUNTS:
        buttons.append([InlineKeyboardButton(
            text=f"{count} вопросов",
            callback_data=f"count:{count}",
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад к выбору темы", callback_data="back_to_topic")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
