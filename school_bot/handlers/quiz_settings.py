"""Question count selection and test generation handler."""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from states.quiz_states import QuizFlow
from keyboards.main_menu import quiz_home_keyboard

router = Router()


@router.callback_query(QuizFlow.choosing_question_count, F.data.startswith("count:"))
async def count_selected(callback: CallbackQuery, state: FSMContext):
    count = int(callback.data.split(":")[1])
    await state.update_data(question_count=count)

    data = await state.get_data()
    language = data["language"]
    topic = data["topic"]

    lang_flag = "🇬🇧" if language == "English" else "🇪🇸"

    await state.set_state(QuizFlow.generating_test)
    await callback.message.edit_text(
        f"⏳ Генерирую тест...\n\n"
        f"{lang_flag} Язык: {language}\n"
        f"📚 Тема: {topic}\n"
        f"❓ Вопросов: {count}\n\n"
        f"Подожди немного, это займёт 10-20 секунд..."
    )
    await callback.answer()

    from services.test_generator import generate_test
    from handlers.quiz import start_quiz

    questions = await generate_test(language, topic, count, user_id=callback.from_user.id)

    if not questions:
        await callback.message.edit_text(
            "😞 Не удалось сгенерировать тест. Возможно, LM Studio не запущен.\n\n"
            "Проверь, что LM Studio работает и модель загружена, затем попробуй снова.",
            reply_markup=quiz_home_keyboard(),
        )
        await state.clear()
        return

    # Load user's gamification theme
    from database.crud import get_user_theme
    theme_key = await get_user_theme(callback.from_user.id)

    await state.update_data(
        questions=questions,
        current_index=0,
        correct_count=0,
        answers=[],
        user_id=callback.from_user.id,
        theme_key=theme_key,
    )
    await start_quiz(callback.message, state)
