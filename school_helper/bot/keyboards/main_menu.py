from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Пройти тест", callback_data="start_test")],
        [InlineKeyboardButton(text="📈 Мои результаты", callback_data="my_results")],
    ])
