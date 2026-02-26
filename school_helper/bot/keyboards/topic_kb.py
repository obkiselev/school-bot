from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.config import TOPICS


def topic_keyboard(language: str) -> InlineKeyboardMarkup:
    topics = TOPICS.get(language, [])
    buttons = []
    for i, topic in enumerate(topics):
        buttons.append([InlineKeyboardButton(text=topic, callback_data=f"topic:{i}")])
    buttons.append([InlineKeyboardButton(text="✏️ Другое (своя тема)", callback_data="topic:custom")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад к выбору языка", callback_data="start_test")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
