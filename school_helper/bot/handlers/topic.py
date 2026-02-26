from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.states.quiz_states import QuizFlow
from bot.config import TOPICS
from bot.keyboards.settings_kb import question_count_keyboard
from bot.keyboards.topic_kb import topic_keyboard

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
    topics = TOPICS.get(language, [])
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
    await state.set_state(QuizFlow.choosing_topic)

    lang_name = "английскому" if language == "English" else "испанскому"
    await callback.message.edit_text(
        f"📚 Выбери тему по {lang_name} языку:",
        reply_markup=topic_keyboard(language),
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
