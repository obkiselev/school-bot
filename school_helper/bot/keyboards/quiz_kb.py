from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


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
    """Keyboard shown during text-input questions (fill_blank, translation)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить тест", callback_data="cancel_quiz")],
    ])
