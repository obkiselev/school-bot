"""Language selection handler for quiz."""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from states.quiz_states import QuizFlow
from keyboards.quiz_kb import language_keyboard, topic_keyboard

router = Router()


@router.callback_query(F.data == "start_test")
async def choose_language(callback: CallbackQuery, state: FSMContext):
    await state.set_state(QuizFlow.choosing_language)
    await callback.message.edit_text(
        "🌍 Выбери язык для тестирования:",
        reply_markup=language_keyboard(),
    )
    await callback.answer()


@router.callback_query(QuizFlow.choosing_language, F.data.startswith("lang:"))
async def language_selected(callback: CallbackQuery, state: FSMContext):
    language = callback.data.split(":")[1]
    await state.update_data(language=language)
    await state.set_state(QuizFlow.choosing_topic)

    lang_name = "английскому" if language == "English" else "испанскому"
    await callback.message.edit_text(
        f"📚 Выбери тему по {lang_name} языку:",
        reply_markup=topic_keyboard(language),
    )
    await callback.answer()
