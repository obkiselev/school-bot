"""Topic selection handler for quiz."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from states.quiz_states import QuizFlow
from config import settings
from keyboards.quiz_kb import question_count_keyboard, topic_keyboard

router = Router()


@router.callback_query(QuizFlow.choosing_topic, F.data.startswith("topic:"))
async def topic_selected(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":")[1]

    if value == "custom":
        await state.set_state(QuizFlow.entering_custom_topic)
        await callback.message.edit_text(
            "✏️ Напиши тему, по которой хочешь пройти тест:"
        )
        await callback.answer()
        return

    data = await state.get_data()
    language = data["language"]
    level = data.get("level", "A2")
    lang_topics = settings.TOPICS.get(language, {})
    if isinstance(lang_topics, dict):
        topics = lang_topics.get(level, [])
    else:
        topics = lang_topics
    topic_index = int(value)
    topic = topics[topic_index]

    await state.update_data(topic=topic)
    await state.set_state(QuizFlow.choosing_question_count)
    await callback.message.edit_text(
        f"📝 Тема: {topic}\n\nСколько вопросов в тесте?",
        reply_markup=question_count_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_topic")
async def back_to_topic(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    language = data.get("language", "English")
    level = data.get("level", "A2")
    await state.set_state(QuizFlow.choosing_topic)

    lang_name = "английскому" if language == "English" else "испанскому"
    await callback.message.edit_text(
        f"📚 Уровень: {level}\n"
        f"Выбери тему по {lang_name} языку:",
        reply_markup=topic_keyboard(language, level),
    )
    await callback.answer()


@router.message(QuizFlow.entering_custom_topic)
async def custom_topic_entered(message: Message, state: FSMContext):
    topic = message.text.strip()
    if not topic:
        await message.answer("Тема не может быть пустой. Напиши тему:")
        return

    await state.update_data(topic=topic)
    await state.set_state(QuizFlow.choosing_question_count)
    await message.answer(
        f"📝 Тема: {topic}\n\nСколько вопросов в тесте?",
        reply_markup=question_count_keyboard(),
    )
