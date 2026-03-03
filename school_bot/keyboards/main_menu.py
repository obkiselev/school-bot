"""Role-based main menu keyboards."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def home_button() -> InlineKeyboardButton:
    """Reusable 'back to main menu' button for any keyboard."""
    return InlineKeyboardButton(text="🏠 Главное меню", callback_data="go_home")


def parent_menu_keyboard() -> InlineKeyboardMarkup:
    """Menu for parents (МЭШ features)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Расписание", callback_data="menu:raspisanie")],
        [InlineKeyboardButton(text="📊 Оценки", callback_data="menu:ocenki")],
        [InlineKeyboardButton(text="📝 Домашние задания", callback_data="menu:dz")],
        [InlineKeyboardButton(text="🔄 Перерегистрировать МЭШ", callback_data="reregister")],
    ])


def student_menu_keyboard() -> InlineKeyboardMarkup:
    """Menu for students (quiz features)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Пройти тест", callback_data="start_test")],
        [InlineKeyboardButton(text="📈 Мои результаты", callback_data="my_results")],
    ])


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Menu for admins (all features)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Расписание", callback_data="menu:raspisanie")],
        [InlineKeyboardButton(text="📊 Оценки", callback_data="menu:ocenki")],
        [InlineKeyboardButton(text="📝 Домашние задания", callback_data="menu:dz")],
        [InlineKeyboardButton(text="🎓 Пройти тест", callback_data="start_test")],
        [InlineKeyboardButton(text="📈 Результаты тестов", callback_data="my_results")],
        [InlineKeyboardButton(text="🔄 Перерегистрировать МЭШ", callback_data="reregister")],
    ])


def quiz_home_keyboard() -> InlineKeyboardMarkup:
    """Home menu for quiz section (back to start)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Пройти тест", callback_data="start_test")],
        [InlineKeyboardButton(text="📈 Мои результаты", callback_data="my_results")],
        [home_button()],
    ])
