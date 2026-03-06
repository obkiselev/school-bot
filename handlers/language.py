"""Language selection handler for quiz."""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from datetime import date

from states.quiz_states import QuizFlow
from keyboards.quiz_kb import language_keyboard, topic_keyboard, level_keyboard
from keyboards.main_menu import quiz_home_keyboard
from services.level_adapter import get_user_level, DEFAULT_LEVEL

router = Router()


@router.message(Command("test"))
async def cmd_test(message: Message, state: FSMContext):
    """Handle /test — start quiz via slash command."""
    await state.clear()
    await state.set_state(QuizFlow.choosing_language)
    await message.answer(
        "🌍 Выбери язык для тестирования:",
        reply_markup=language_keyboard(),
    )


@router.callback_query(F.data == "start_test")
async def choose_language(callback: CallbackQuery, state: FSMContext):
    await state.set_state(QuizFlow.choosing_language)
    await callback.message.edit_text(
        "🌍 Выбери язык для тестирования:",
        reply_markup=language_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "daily_challenge")
async def daily_challenge(callback: CallbackQuery, state: FSMContext):
    """Handle daily challenge button."""
    from database.crud import get_daily_challenge, get_weak_topics
    user_id = callback.from_user.id
    today = date.today().isoformat()

    challenge = await get_daily_challenge(user_id, today)
    if challenge and challenge["is_completed"]:
        await callback.message.edit_text(
            "\u2705 \u0422\u044b \u0443\u0436\u0435 \u0432\u044b\u043f\u043e\u043b\u043d\u0438\u043b \u0437\u0430\u0434\u0430\u043d\u0438\u0435 \u0434\u043d\u044f! \u041f\u0440\u0438\u0445\u043e\u0434\u0438 \u0437\u0430\u0432\u0442\u0440\u0430.",
            reply_markup=quiz_home_keyboard(),
        )
        await callback.answer()
        return

    if challenge:
        # Start quiz with the challenge topic
        user_level = await get_user_level(user_id, challenge["subject"]) or DEFAULT_LEVEL
        await state.update_data(language=challenge["subject"], topic=challenge["topic"], level=user_level)
        await state.set_state(QuizFlow.choosing_question_count)
        from keyboards.quiz_kb import question_count_keyboard
        await callback.message.edit_text(
            f"\U0001f3af \u0417\u0430\u0434\u0430\u043d\u0438\u0435 \u0434\u043d\u044f!\n\n"
            f"\U0001f4da \u0422\u0435\u043c\u0430: {challenge['topic']}\n"
            f"\U0001f4b0 \u041d\u0430\u0433\u0440\u0430\u0434\u0430: +{challenge['xp_reward']} XP\n\n"
            f"\u0412\u044b\u0431\u0435\u0440\u0438 \u043a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e \u0432\u043e\u043f\u0440\u043e\u0441\u043e\u0432:",
            reply_markup=question_count_keyboard(),
        )
        await callback.answer()
        return

    # No challenge created yet — create one from weak topics
    weak = await get_weak_topics(user_id)
    if weak:
        topic_data = weak[0]
        subject = topic_data["language"]
        topic = topic_data["topic"]
    else:
        subject = "English"
        topic = "General Vocabulary"

    from database.crud import create_daily_challenge
    await create_daily_challenge(user_id, today, subject, topic)

    user_level = await get_user_level(user_id, subject) or DEFAULT_LEVEL
    await state.update_data(language=subject, topic=topic, level=user_level)
    await state.set_state(QuizFlow.choosing_question_count)
    from keyboards.quiz_kb import question_count_keyboard
    await callback.message.edit_text(
        f"\U0001f3af \u0417\u0430\u0434\u0430\u043d\u0438\u0435 \u0434\u043d\u044f!\n\n"
        f"\U0001f4da \u0422\u0435\u043c\u0430: {topic}\n"
        f"\U0001f4b0 \u041d\u0430\u0433\u0440\u0430\u0434\u0430: +50 XP\n\n"
        f"\u0412\u044b\u0431\u0435\u0440\u0438 \u043a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e \u0432\u043e\u043f\u0440\u043e\u0441\u043e\u0432:",
        reply_markup=question_count_keyboard(),
    )
    await callback.answer()


@router.callback_query(QuizFlow.choosing_language, F.data.startswith("lang:"))
async def language_selected(callback: CallbackQuery, state: FSMContext):
    language = callback.data.split(":")[1]
    await state.update_data(language=language)

    user_id = callback.from_user.id
    auto_level = await get_user_level(user_id, language)

    if auto_level:
        # Student — level auto-detected, skip to topic selection
        await state.update_data(level=auto_level)
        await state.set_state(QuizFlow.choosing_topic)
        lang_name = "английскому" if language == "English" else "испанскому"
        await callback.message.edit_text(
            f"📚 Уровень: {auto_level}\n"
            f"Выбери тему по {lang_name} языку:",
            reply_markup=topic_keyboard(language, auto_level),
        )
    else:
        # Parent/admin — show level selection
        await state.set_state(QuizFlow.choosing_level)
        await callback.message.edit_text(
            f"📊 Выбери уровень сложности:",
            reply_markup=level_keyboard(language),
        )
    await callback.answer()


@router.callback_query(QuizFlow.choosing_level, F.data.startswith("level:"))
async def level_selected(callback: CallbackQuery, state: FSMContext):
    level = callback.data.split(":")[1]
    data = await state.get_data()
    language = data["language"]
    await state.update_data(level=level)
    await state.set_state(QuizFlow.choosing_topic)

    lang_name = "английскому" if language == "English" else "испанскому"
    await callback.message.edit_text(
        f"📚 Уровень: {level}\n"
        f"Выбери тему по {lang_name} языку:",
        reply_markup=topic_keyboard(language, level),
    )
    await callback.answer()
