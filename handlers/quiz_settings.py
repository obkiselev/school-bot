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
    level = data.get("level", "A2")

    lang_flag_map = {
        "English": "🇬🇧",
        "Spanish": "🇪🇸",
        "French": "🇫🇷",
        "German": "🇩🇪",
        "Mathematics": "📐",
        "History": "🏛",
        "Biology": "🧬",
    }
    lang_flag = lang_flag_map.get(language, "📘")

    await state.set_state(QuizFlow.generating_test)
    await callback.message.edit_text(
        f"⏳ Генерирую тест...\n\n"
        f"{lang_flag} Язык: {language}\n"
        f"📊 Уровень: {level}\n"
        f"📚 Тема: {topic}\n"
        f"❓ Вопросов: {count}\n\n"
        f"Подожди немного, это займёт 10-20 секунд..."
    )
    await callback.answer()

    from services.test_generator import generate_test
    from handlers.quiz import start_quiz

    questions = await generate_test(language, topic, count, user_id=callback.from_user.id, level=level)

    if not questions:
        await callback.message.edit_text(
            "😞 Не удалось сгенерировать тест. Возможно, LM Studio не запущен.\n\n"
            "Проверь, что LM Studio работает и модель загружена, затем попробуй снова.",
            reply_markup=quiz_home_keyboard(),
        )
        await state.clear()
        return

    source = questions[0].get("_source", "llm")
    mode_text_map = {"llm": "LLM", "fallback": "fallback", "imported": "imported"}
    mode_text = mode_text_map.get(source, source)
    if source == "fallback":
        reason = (questions[0].get("_source_reason") or "LLM недоступен").strip()
        if len(reason) > 140:
            reason = reason[:137] + "..."
        await callback.message.answer(f"ℹ️ Режим: {mode_text}\nПричина: {reason}")
    elif source == "imported":
        await callback.message.answer("ℹ️ Режим: imported (вопросы из загруженного файла)")
    else:
        await callback.message.answer(f"ℹ️ Режим: {mode_text}")

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
