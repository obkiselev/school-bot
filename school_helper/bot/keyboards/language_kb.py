from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:English")],
        [InlineKeyboardButton(text="🇪🇸 Español", callback_data="lang:Spanish")],
        [InlineKeyboardButton(text="🏠 Назад", callback_data="go_home")],
    ])
