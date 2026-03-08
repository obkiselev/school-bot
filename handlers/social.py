"""Competitions and social features (v1.5.0)."""
from datetime import date, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.crud import (
    create_shared_result,
    get_last_test_session,
    get_shared_result,
    get_user_badges,
    get_user_role,
    get_user_stats,
    get_user_weekly_tests_rank,
    get_user_xp_rank,
    get_weekly_tests_leaderboard,
    get_xp_leaderboard,
)
from keyboards.main_menu import social_menu_keyboard

router = Router()


def _week_bounds(today: date) -> tuple[date, date]:
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return start, end


async def _ensure_student_message(message: Message) -> bool:
    role = await get_user_role(message.from_user.id)
    if role != "student":
        await message.answer("Эта функция доступна только ученикам.")
        return False
    return True


async def _ensure_student_callback(callback: CallbackQuery) -> bool:
    role = await get_user_role(callback.from_user.id)
    if role != "student":
        await callback.answer("Только для учеников", show_alert=True)
        return False
    return True


def _format_shared_result_text(data: dict) -> str:
    score = f"{data['correct_answers']}/{data['total_questions']} ({data['score_percent']}%)"
    return (
        "🤝 Поделились результатом\n\n"
        f"👤 Ученик: {data['sender_name']}\n"
        f"📚 Предмет: {data['language']}\n"
        f"🧩 Тема: {data['topic']}\n"
        f"📊 Результат: {score}\n"
        f"🕒 Дата: {data['finished_at']}"
    )


@router.message(Command("social"))
async def cmd_social(message: Message, state: FSMContext):
    """Open social hub."""
    if not await _ensure_student_message(message):
        return
    await state.clear()
    await message.answer(
        "🏆 Соревнования и социальные функции\n\nВыбери раздел:",
        reply_markup=social_menu_keyboard(),
    )


@router.message(Command("share"))
async def cmd_share(message: Message):
    """Open shared result by token: /share <token>."""
    if not await _ensure_student_message(message):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /share <token>")
        return

    token = parts[1].strip()
    shared = await get_shared_result(token)
    if not shared:
        await message.answer("Ссылка недействительна или устарела.")
        return

    await message.answer(_format_shared_result_text(shared), reply_markup=social_menu_keyboard())


@router.callback_query(F.data.in_({"menu:social", "social:hub"}))
async def cb_social_hub(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_student_callback(callback):
        return
    await state.clear()
    await callback.message.edit_text(
        "🏆 Соревнования и социальные функции\n\nВыбери раздел:",
        reply_markup=social_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "social:leaderboard")
async def cb_social_leaderboard(callback: CallbackQuery):
    if not await _ensure_student_callback(callback):
        return

    leaders = await get_xp_leaderboard(limit=10)
    my_rank = await get_user_xp_rank(callback.from_user.id)

    lines = ["🏆 Таблица лидеров по XP\n"]
    if not leaders:
        lines.append("Пока нет данных по тестам.")
    else:
        medals = ["🥇", "🥈", "🥉"]
        for idx, item in enumerate(leaders, start=1):
            prefix = medals[idx - 1] if idx <= 3 else f"{idx}."
            lines.append(
                f"{prefix} {item['display_name']} — {item['xp_total']} XP "
                f"(ур. {item['level']}, серия {item['current_streak']} дн.)"
            )

    lines.append("")
    lines.append(f"Твоя позиция: #{my_rank}" if my_rank else "Твоя позиция: пока нет в рейтинге")
    await callback.message.edit_text("\n".join(lines), reply_markup=social_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "social:weekly")
async def cb_social_weekly(callback: CallbackQuery):
    if not await _ensure_student_callback(callback):
        return

    start, end = _week_bounds(date.today())
    leaders = await get_weekly_tests_leaderboard(start.isoformat(), end.isoformat(), limit=10)
    me = await get_user_weekly_tests_rank(callback.from_user.id, start.isoformat(), end.isoformat())

    lines = [
        "⚔️ Еженедельный челлендж",
        f"Период: {start.strftime('%d.%m')}–{end.strftime('%d.%m')}\n",
    ]

    if not leaders:
        lines.append("На этой неделе пока никто не прошёл тест.")
    else:
        medals = ["🥇", "🥈", "🥉"]
        for idx, item in enumerate(leaders, start=1):
            prefix = medals[idx - 1] if idx <= 3 else f"{idx}."
            lines.append(
                f"{prefix} {item['display_name']} — {item['tests_count']} тест(ов), "
                f"ср. {item['avg_score']}%"
            )

    lines.append("")
    if me:
        lines.append(
            f"Твой результат: #{me['rank']} | {me['tests_count']} тест(ов) | "
            f"ср. {me['avg_score']}%"
        )
    else:
        lines.append("Твой результат: на этой неделе тестов пока нет")

    await callback.message.edit_text("\n".join(lines), reply_markup=social_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "social:regularity")
async def cb_social_regularity(callback: CallbackQuery):
    if not await _ensure_student_callback(callback):
        return

    user_id = callback.from_user.id
    stats = await get_user_stats(user_id)
    badges = set(await get_user_badges(user_id))

    streak = stats["current_streak"] if stats else 0
    longest = stats["longest_streak"] if stats else 0

    milestones = [
        ("streak_3", 3, "3 дня подряд"),
        ("streak_7", 7, "7 дней подряд"),
        ("streak_30", 30, "30 дней подряд"),
    ]

    lines = [
        "🔥 Достижения за регулярность\n",
        f"Текущая серия: {streak} дн.",
        f"Лучшая серия: {longest} дн.\n",
    ]

    for badge_key, target, title in milestones:
        done = streak >= target or badge_key in badges
        marker = "✅" if done else "⬜"
        progress = min(streak, target)
        lines.append(f"{marker} {title} ({progress}/{target})")

    await callback.message.edit_text("\n".join(lines), reply_markup=social_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "social:share_last")
async def cb_social_share_last(callback: CallbackQuery):
    if not await _ensure_student_callback(callback):
        return

    user_id = callback.from_user.id
    last = await get_last_test_session(user_id)
    if not last:
        await callback.message.edit_text(
            "Пока нечем делиться: сначала пройди хотя бы один тест.",
            reply_markup=social_menu_keyboard(),
        )
        await callback.answer()
        return

    token = await create_shared_result(user_id, last["id"])
    await callback.message.edit_text(
        "🤝 Обмен результатами\n\n"
        "Отправь другу эту команду:\n"
        f"`/share {token}`\n\n"
        "Тот, кто выполнит её в боте, увидит твой последний результат.",
        parse_mode="Markdown",
        reply_markup=social_menu_keyboard(),
    )
    await callback.answer()
