"""Обработчик аналитики оценок — средние баллы, тренды, распределение."""
import logging
from typing import List, Optional, Tuple

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database.crud import get_user, get_user_children, invalidate_token
from keyboards.main_menu import home_button, back_button
from mesh_api.client import MeshClient
from mesh_api.exceptions import AuthenticationError, MeshAPIError
from mesh_api.models import Grade
from services.analytics import get_analytics_periods, format_analytics
from utils.token_manager import ensure_token

logger = logging.getLogger(__name__)

router = Router()


# ============================================================================
# КЛАВИАТУРЫ
# ============================================================================

def _get_period_keyboard(student_id: int) -> InlineKeyboardMarkup:
    """Кнопки переключения периода аналитики."""
    buttons = [
        [
            InlineKeyboardButton(
                text="\U0001f4c5 Неделя",
                callback_data=f"analytics:period:{student_id}:week"
            ),
            InlineKeyboardButton(
                text="\U0001f4c5 Месяц",
                callback_data=f"analytics:period:{student_id}:month"
            ),
            InlineKeyboardButton(
                text="\U0001f4c5 Четверть",
                callback_data=f"analytics:period:{student_id}:quarter"
            ),
        ],
        [back_button("analytics:back"), home_button()],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _get_retry_keyboard(student_id: int, period: str) -> InlineKeyboardMarkup:
    """Кнопка повторной попытки после ошибки."""
    buttons = [
        [
            InlineKeyboardButton(
                text="\U0001f504 Повторить",
                callback_data=f"analytics:retry:{student_id}:{period}"
            )
        ],
        [back_button("analytics:back"), home_button()],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _get_child_keyboard(children: List[dict]) -> InlineKeyboardMarkup:
    """Кнопки выбора ребёнка для аналитики."""
    buttons = []
    for child in children:
        full_name = f"{child['last_name']} {child['first_name']}"
        if child.get("class_name"):
            full_name += f" ({child['class_name']})"

        buttons.append([
            InlineKeyboardButton(
                text=full_name,
                callback_data=f"analytics:child:{child['student_id']}"
            )
        ])
    buttons.append([home_button()])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _home_only_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[home_button()]])


def _reregister_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f504 Перерегистрировать МЭШ", callback_data="reregister")],
        [home_button()],
    ])


def _parse_callback_data(data: str) -> Optional[tuple]:
    """Парсит callback_data формата analytics:action:student_id[:extra]."""
    try:
        parts = data.split(":")
        if len(parts) < 3 or parts[0] != "analytics":
            return None
        action = parts[1]
        student_id = int(parts[2])
        extra = parts[3] if len(parts) > 3 else None
        return (action, student_id, extra)
    except (ValueError, IndexError):
        return None


# ============================================================================
# БИЗНЕС-ЛОГИКА
# ============================================================================

async def _fetch_grades(
    student_id: int,
    from_date: str,
    to_date: str,
    token: str,
    profile_id: Optional[int] = None,
) -> List[Grade]:
    """Получает оценки за указанный период из МЭШ API."""
    client = MeshClient()
    try:
        return await client.get_grades(
            student_id=student_id,
            from_date=from_date,
            to_date=to_date,
            token=token,
            profile_id=profile_id,
        )
    finally:
        await client.close()


async def _get_analytics_text(
    student_id: int,
    period: str,
    token: str,
    profile_id: Optional[int] = None,
) -> Tuple[str, InlineKeyboardMarkup]:
    """Получает текст аналитики и клавиатуру.

    Делает 2 вызова API: текущий период + предыдущий для сравнения.

    Raises:
        AuthenticationError, MeshAPIError
    """
    (cur_from, cur_to), (prev_from, prev_to) = get_analytics_periods(period)

    current_grades = await _fetch_grades(
        student_id, cur_from.isoformat(), cur_to.isoformat(),
        token, profile_id,
    )
    previous_grades = await _fetch_grades(
        student_id, prev_from.isoformat(), prev_to.isoformat(),
        token, profile_id,
    )

    text = format_analytics(current_grades, previous_grades, period)
    keyboard = _get_period_keyboard(student_id)
    return text, keyboard


# ============================================================================
# ОБЩАЯ ЛОГИКА CALLBACK-ОБРАБОТЧИКОВ
# ============================================================================

async def _handle_analytics_request(
    callback: CallbackQuery,
    student_id: int,
    period: str
) -> None:
    """Общая логика: IDOR check -> token -> fetch -> format -> edit message."""
    user_id = callback.from_user.id

    # IDOR-проверка
    children = await get_user_children(user_id)
    child_map = {c["student_id"]: c for c in children}
    if student_id not in child_map:
        logger.warning("Попытка IDOR: user %d запросил аналитику student %d", user_id, student_id)
        return

    # profile_id
    user = await get_user(user_id)
    profile_id = user.get("mesh_profile_id") if user else None

    if not profile_id:
        await callback.message.edit_text(
            "\u274c Для просмотра аналитики необходимо перерегистрировать МЭШ-аккаунт.",
            reply_markup=_reregister_keyboard(),
        )
        return

    # Токен
    try:
        token = await ensure_token(user_id)
    except AuthenticationError as e:
        logger.error("Ошибка авторизации МЭШ для user_id=%d: %s", user_id, e)
        await callback.message.edit_text(
            f"\u274c {e}",
            reply_markup=_home_only_keyboard(),
        )
        return

    try:
        text, keyboard = await _get_analytics_text(
            student_id, period, token, profile_id=profile_id,
        )
        await callback.message.edit_text(
            text, reply_markup=keyboard, parse_mode="HTML"
        )
    except AuthenticationError:
        logger.warning("Токен 401 для user_id=%d, пробуем переавторизацию", user_id)
        try:
            await invalidate_token(user_id)
            token = await ensure_token(user_id)
            text, keyboard = await _get_analytics_text(
                student_id, period, token, profile_id=profile_id,
            )
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode="HTML"
            )
        except AuthenticationError as e2:
            logger.error("Повторная авторизация не помогла для user_id=%d: %s", user_id, e2)
            await callback.message.edit_text(
                f"\u274c {e2}",
                reply_markup=_home_only_keyboard(),
            )
    except MeshAPIError as e:
        logger.error("Ошибка API МЭШ (аналитика) для user_id=%d: %s", user_id, e)
        retry_keyboard = _get_retry_keyboard(student_id, period)
        await callback.message.edit_text(
            "\u26a0\ufe0f Сервис МЭШ временно недоступен, попробуйте позже",
            reply_markup=retry_keyboard
        )


# ============================================================================
# ОБРАБОТЧИКИ CALLBACK
# ============================================================================

@router.callback_query(F.data.startswith("analytics:period:"))
async def cb_analytics_period(callback: CallbackQuery):
    """Обработчик выбора периода аналитики."""
    await callback.answer()

    parsed = _parse_callback_data(callback.data)
    if parsed is None:
        logger.warning("Невалидный callback_data: %s", callback.data)
        return

    _, student_id, period = parsed

    if period not in ("week", "month", "quarter"):
        logger.warning("Неизвестный период аналитики: %s", callback.data)
        return

    await _handle_analytics_request(callback, student_id, period)


@router.callback_query(F.data.startswith("analytics:child:"))
async def cb_analytics_child(callback: CallbackQuery):
    """Обработчик выбора ребёнка для аналитики."""
    await callback.answer()

    parsed = _parse_callback_data(callback.data)
    if parsed is None:
        logger.warning("Невалидный callback_data: %s", callback.data)
        return

    _, student_id, _ = parsed
    await _handle_analytics_request(callback, student_id, "week")


@router.callback_query(F.data.startswith("analytics:retry:"))
async def cb_analytics_retry(callback: CallbackQuery):
    """Обработчик кнопки 'Повторить' после ошибки."""
    await callback.answer()

    parsed = _parse_callback_data(callback.data)
    if parsed is None:
        logger.warning("Невалидный callback_data: %s", callback.data)
        return

    _, student_id, period = parsed

    if period not in ("week", "month", "quarter"):
        logger.warning("Неизвестный период аналитики: %s", callback.data)
        return

    await _handle_analytics_request(callback, student_id, period)


@router.callback_query(F.data == "analytics:back")
async def cb_analytics_back(callback: CallbackQuery):
    """Назад: к выбору ребёнка (если >1) или к оценкам."""
    await callback.answer()
    user_id = callback.from_user.id

    children = await get_user_children(user_id)
    if len(children) > 1:
        keyboard = _get_child_keyboard(children)
        await callback.message.edit_text(
            "Выберите ребёнка для аналитики оценок:",
            reply_markup=keyboard,
        )
    else:
        from keyboards.main_menu import full_menu_keyboard, student_menu_keyboard
        from database.crud import get_user_role
        role = await get_user_role(user_id)
        if role == "student":
            await callback.message.edit_text(
                "\U0001f44b Выбери, что хочешь сделать:",
                reply_markup=student_menu_keyboard(),
            )
        else:
            await callback.message.edit_text(
                "Главное меню:",
                reply_markup=full_menu_keyboard(),
            )
