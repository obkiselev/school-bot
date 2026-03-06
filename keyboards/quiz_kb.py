"""Quiz inline keyboards."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import settings
from keyboards.main_menu import home_button
from services.level_adapter import AVAILABLE_LEVELS


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:English")],
        [InlineKeyboardButton(text="🇪🇸 Español", callback_data="lang:Spanish")],
        [home_button()],
    ])


def level_keyboard(language: str) -> InlineKeyboardMarkup:
    """Keyboard for manual CEFR level selection (parent/admin)."""
    levels = AVAILABLE_LEVELS.get(language, ["A2"])
    buttons = []
    for lvl in levels:
        desc = settings.LEVEL_DESCRIPTIONS.get(lvl, "")
        short_desc = desc.split("(")[0].strip() if desc else lvl
        buttons.append([InlineKeyboardButton(
            text=f"{lvl} — {short_desc}",
            callback_data=f"level:{lvl}",
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад к выбору языка", callback_data="start_test")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def topic_keyboard(language: str, level: str | None = None) -> InlineKeyboardMarkup:
    lang_topics = settings.TOPICS.get(language, {})
    if isinstance(lang_topics, dict) and level:
        topics = lang_topics.get(level, [])
    elif isinstance(lang_topics, list):
        topics = lang_topics
    else:
        topics = []
    buttons = []
    for i, topic in enumerate(topics):
        buttons.append([InlineKeyboardButton(text=topic, callback_data=f"topic:{i}")])
    buttons.append([InlineKeyboardButton(text="✏️ Другое (своя тема)", callback_data="topic:custom")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад к выбору языка", callback_data="start_test")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def question_count_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for count in settings.QUESTION_COUNTS:
        buttons.append([InlineKeyboardButton(
            text=f"{count} вопросов",
            callback_data=f"count:{count}",
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад к выбору темы", callback_data="back_to_topic")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def multiple_choice_keyboard(options: list[str]) -> InlineKeyboardMarkup:
    labels = ["A", "B", "C", "D"]
    buttons = []
    for i, option in enumerate(options[:4]):
        label = labels[i] if i < len(labels) else str(i + 1)
        buttons.append([InlineKeyboardButton(
            text=f"{label}) {option}",
            callback_data=f"ans:{option}",
        )])
    buttons.append([InlineKeyboardButton(text="❌ Отменить тест", callback_data="cancel_quiz")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def true_false_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ True", callback_data="ans:True"),
            InlineKeyboardButton(text="❌ False", callback_data="ans:False"),
        ],
        [InlineKeyboardButton(text="❌ Отменить тест", callback_data="cancel_quiz")],
    ])


def cancel_keyboard() -> InlineKeyboardMarkup:
    """Keyboard shown during text-input questions."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить тест", callback_data="cancel_quiz")],
    ])
