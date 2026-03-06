"""Role-based main menu keyboards."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def home_button() -> InlineKeyboardButton:
    """Reusable 'back to main menu' button for any keyboard."""
    return InlineKeyboardButton(text="🏠 Главное меню", callback_data="go_home")


def back_button(callback_data: str) -> InlineKeyboardButton:
    """Reusable 'back one step' button for any keyboard."""
    return InlineKeyboardButton(text="◀️ Назад", callback_data=callback_data)


def full_menu_keyboard() -> InlineKeyboardMarkup:
    """Full menu for admin and parent (all features)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Расписание", callback_data="menu:raspisanie")],
        [InlineKeyboardButton(text="📊 Оценки", callback_data="menu:ocenki")],
        [InlineKeyboardButton(text="📝 Домашние задания", callback_data="menu:dz")],
        [InlineKeyboardButton(text="🎓 Пройти тест", callback_data="start_test")],
        [InlineKeyboardButton(text="📈 Результаты тестов", callback_data="my_results")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile"),
         InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings")],
        [InlineKeyboardButton(text="🔄 Перерегистрировать МЭШ", callback_data="reregister")],
    ])


def student_menu_keyboard() -> InlineKeyboardMarkup:
    """Menu for students (schedule, homework, tests — no grades)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Расписание уроков", callback_data="menu:raspisanie")],
        [InlineKeyboardButton(text="📝 Домашние задания", callback_data="menu:dz")],
        [InlineKeyboardButton(text="🎓 Пройти тест", callback_data="start_test")],
        [InlineKeyboardButton(text="📈 Результаты тестов", callback_data="my_results")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile"),
         InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings")],
        [InlineKeyboardButton(text="🔄 Перерегистрировать МЭШ", callback_data="reregister")],
    ])


def quiz_home_keyboard() -> InlineKeyboardMarkup:
    """Home menu for quiz section (back to start)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f4dd \u041f\u0440\u043e\u0439\u0442\u0438 \u0442\u0435\u0441\u0442", callback_data="start_test")],
        [InlineKeyboardButton(text="\U0001f3af \u0417\u0430\u0434\u0430\u043d\u0438\u0435 \u0434\u043d\u044f", callback_data="daily_challenge")],
        [InlineKeyboardButton(text="\U0001f4c8 \u041c\u043e\u0438 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u044b", callback_data="my_results")],
        [home_button()],
    ])
