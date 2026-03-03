"""Quiz history and statistics handler."""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards.main_menu import quiz_home_keyboard
from services.progress_tracker import format_history, format_weak_areas, format_overall_stats

router = Router()


@router.callback_query(F.data == "my_results")
async def show_history(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    user_id = callback.from_user.id

    history = await format_history(user_id)
    weak = await format_weak_areas(user_id)
    stats = await format_overall_stats(user_id)

    text = history
    if weak:
        text += "\n" + weak
    if stats:
        text += "\n" + stats

    await callback.message.edit_text(text, reply_markup=quiz_home_keyboard())
    await callback.answer()
