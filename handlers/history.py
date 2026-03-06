"""Quiz history and statistics handler."""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards.main_menu import quiz_home_keyboard
from services.progress_tracker import format_history, format_weak_areas, format_overall_stats
from services.gamification import format_gamification_header
from database.crud import get_user_stats, get_user_badges

router = Router()


@router.callback_query(F.data == "my_results")
async def show_history(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    user_id = callback.from_user.id

    # Gamification header
    gamification_header = ""
    stats = await get_user_stats(user_id)
    if stats:
        badges = await get_user_badges(user_id)
        gamification_header = format_gamification_header(
            theme_key=stats.get("theme") or "neutral",
            streak=stats.get("current_streak", 0),
            level=stats.get("level", 1),
            xp_total=stats.get("xp_total", 0),
            badge_count=len(badges),
        ) + "\n\n"

    history = await format_history(user_id)
    weak = await format_weak_areas(user_id)
    overall = await format_overall_stats(user_id)

    text = gamification_header + history
    if weak:
        text += "\n" + weak
    if overall:
        text += "\n" + overall

    await callback.message.edit_text(text, reply_markup=quiz_home_keyboard())
    await callback.answer()
