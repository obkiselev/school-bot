from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.keyboards.main_menu import main_menu_keyboard
from bot.states.quiz_states import QuizFlow

router = Router()


async def show_results(message: Message, state: FSMContext):
    """Show the final quiz results."""
    data = await state.get_data()
    language = data.get("language", "")
    topic = data.get("topic", "")
    total = data.get("question_count", 0)
    correct = data.get("correct_count", 0)
    answers = data.get("answers", [])

    # Calculate actual totals from answers
    actual_total = len(answers)
    if actual_total == 0:
        actual_total = total
    percent = round(correct / actual_total * 100) if actual_total > 0 else 0

    # Pick an emoji based on score
    if percent >= 90:
        emoji = "🏆"
        comment = "Отличный результат!"
    elif percent >= 70:
        emoji = "👍"
        comment = "Хороший результат!"
    elif percent >= 50:
        emoji = "📖"
        comment = "Неплохо, но есть над чем поработать."
    else:
        emoji = "💪"
        comment = "Нужно ещё потренироваться. Ты справишься!"

    lang_flag = "🇬🇧" if language == "English" else "🇪🇸"

    text = (
        f"📊 Результаты теста\n\n"
        f"{lang_flag} Язык: {language}\n"
        f"📚 Тема: {topic}\n\n"
        f"{emoji} Правильных: {correct} из {actual_total} ({percent}%)\n\n"
        f"{comment}"
    )

    # Save to database
    try:
        from bot.db.queries import save_test_session
        user_id = data.get("user_id")
        if user_id:
            await save_test_session(user_id, language, topic, actual_total, correct, percent, answers)
    except Exception:
        pass  # DB not available yet — silently skip

    await state.clear()
    await message.answer(text, reply_markup=main_menu_keyboard())
