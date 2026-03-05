"""Обработчик команды /ocenki — оценки из МЭШ."""
import html
import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import List, Optional, Tuple

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database.crud import get_user, get_user_children, get_user_role, invalidate_token
from keyboards.main_menu import home_button, back_button
from mesh_api.client import MeshClient
from mesh_api.exceptions import AuthenticationError, MeshAPIError
from mesh_api.models import Grade
from utils.token_manager import ensure_token

logger = logging.getLogger(__name__)

router = Router()

# Названия дней недели на русском
_WEEKDAY_NAMES = [
    "понедельник", "вторник", "среда", "четверг",
    "пятница", "суббота", "воскресенье"
]

# Названия месяцев на русском (родительный падеж)
_MONTH_NAMES = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря"
]

# Лимит длины сообщения Telegram (с запасом)
_MAX_MESSAGE_LEN = 3800


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def _get_period_dates(period: str) -> Tuple[date, date]:
    """Возвращает (from_date, to_date) для указанного периода."""
    today = date.today()
    if period == "week":
        return (today - timedelta(days=6), today)
    elif period == "month":
        return (today - timedelta(days=29), today)
    else:  # today
        return (today, today)


def _get_period_label(period: str) -> str:
    """Возвращает человекочитаемое название периода."""
    labels = {
        "today": "за сегодня",
        "week": "за неделю",
        "month": "за месяц",
    }
    return labels.get(period, "за сегодня")


def _format_day_header(day_date: date) -> str:
    """Форматирует заголовок дня: '3 марта (вторник)'."""
    day_num = day_date.day
    month_name = _MONTH_NAMES[day_date.month]
    weekday_name = _WEEKDAY_NAMES[day_date.weekday()]
    return f"{day_num} {month_name} ({weekday_name})"


def _format_grade_line(grade: Grade) -> str:
    """Форматирует одну оценку."""
    subject = html.escape(grade.subject)
    value = html.escape(grade.grade_value)

    line = f"  {subject} — <b>{value}</b>"
    if grade.lesson_type:
        line += f" ({html.escape(grade.lesson_type)})"

    if grade.comment:
        line += f"\n     \U0001f4ac {html.escape(grade.comment)}"

    return line


def _format_grades(grades: List[Grade], period: str) -> str:
    """Форматирует полное сообщение с оценками."""
    label = _get_period_label(period)
    header = f"<b>\U0001f4ca Оценки {label}</b>\n"

    if not grades:
        return f"{header}\n\U0001f4ed За выбранный период оценок нет"

    # Группировка по дате (новые сверху)
    by_date = defaultdict(list)
    for grade in grades:
        by_date[grade.date].append(grade)

    sorted_dates = sorted(by_date.keys(), reverse=True)

    lines = [header]
    total_grades = 0
    truncated = False

    for day_date in sorted_dates:
        day_header = f"\n<b>{_format_day_header(day_date)}</b>"
        day_lines = [day_header]

        for grade in by_date[day_date]:
            day_lines.append(_format_grade_line(grade))

        day_block = "\n".join(day_lines)

        # Проверка длины
        current_len = len("\n".join(lines))
        if current_len + len(day_block) > _MAX_MESSAGE_LEN:
            remaining = sum(len(by_date[d]) for d in sorted_dates) - total_grades
            lines.append(f"\n... и ещё {remaining} оценок")
            truncated = True
            break

        lines.append(day_block)
        total_grades += len(by_date[day_date])

    return "\n".join(lines)


# ============================================================================
# КЛАВИАТУРЫ
# ============================================================================

def _get_period_keyboard(student_id: int) -> InlineKeyboardMarkup:
    """Кнопки переключения периода."""
    buttons = [
        [
            InlineKeyboardButton(
                text="\U0001f4c5 Сегодня",
                callback_data=f"ocenki:period:{student_id}:today"
            ),
            InlineKeyboardButton(
                text="\U0001f4c5 Неделя",
                callback_data=f"ocenki:period:{student_id}:week"
            ),
            InlineKeyboardButton(
                text="\U0001f4c5 Месяц",
                callback_data=f"ocenki:period:{student_id}:month"
            ),
        ],
        [back_button("ocenki:back"), home_button()],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _get_retry_keyboard(student_id: int, period: str) -> InlineKeyboardMarkup:
    """Кнопка повторной попытки после ошибки."""
    buttons = [
        [
            InlineKeyboardButton(
                text="\U0001f504 Повторить",
                callback_data=f"ocenki:retry:{student_id}:{period}"
            )
        ],
        [back_button("ocenki:back"), home_button()],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _get_child_keyboard(children: List[dict]) -> InlineKeyboardMarkup:
    """Кнопки выбора ребёнка."""
    buttons = []
    for child in children:
        full_name = f"{child['last_name']} {child['first_name']}"
        if child.get("class_name"):
            full_name += f" ({child['class_name']})"

        buttons.append([
            InlineKeyboardButton(
                text=full_name,
                callback_data=f"ocenki:child:{child['student_id']}"
            )
        ])
    buttons.append([home_button()])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _home_only_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с одной кнопкой «Главное меню»."""
    return InlineKeyboardMarkup(inline_keyboard=[[home_button()]])


def _reregister_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопками «Перерегистрировать МЭШ» и «Главное меню»."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f504 Перерегистрировать МЭШ", callback_data="reregister")],
        [home_button()],
    ])


def _parse_callback_data(data: str) -> Optional[tuple]:
    """
    Парсит callback_data формата ocenki:action:student_id[:extra].

    Returns:
        Tuple (action, student_id, extra) или None при ошибке.
    """
    try:
        parts = data.split(":")
        if len(parts) < 3 or parts[0] != "ocenki":
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

async def _get_grades_text(
    student_id: int, period: str, token: str,
    profile_id: Optional[int] = None,
) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Получает текст оценок и клавиатуру для указанного периода.

    Returns:
        Tuple (текст_сообщения, клавиатура)

    Raises:
        AuthenticationError: Проблема с авторизацией
        MeshAPIError: Ошибка API
    """
    from_date, to_date = _get_period_dates(period)

    client = MeshClient()
    try:
        grades = await client.get_grades(
            student_id=student_id,
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
            token=token,
            profile_id=profile_id,
        )
    finally:
        await client.close()

    text = _format_grades(grades, period)
    keyboard = _get_period_keyboard(student_id)
    return text, keyboard


# ============================================================================
# ОБЩАЯ ЛОГИКА CALLBACK-ОБРАБОТЧИКОВ
# ============================================================================

async def _handle_grades_request(
    callback: CallbackQuery,
    student_id: int,
    period: str
) -> None:
    """Общая логика: IDOR check -> token -> fetch -> format -> edit message."""
    user_id = callback.from_user.id

    # IDOR-проверка: ребёнок принадлежит пользователю
    children = await get_user_children(user_id)
    child_map = {c["student_id"]: c for c in children}
    if student_id not in child_map:
        logger.warning("Попытка IDOR: user %d запросил student %d", user_id, student_id)
        return

    # Получаем profile_id пользователя (нужен для API оценок)
    user = await get_user(user_id)
    profile_id = user.get("mesh_profile_id") if user else None

    if not profile_id:
        await callback.message.edit_text(
            "\u274c Для просмотра оценок необходимо перерегистрировать МЭШ-аккаунт.",
            reply_markup=_reregister_keyboard(),
        )
        return

    # Получаем токен (с retry при 401)
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
        text, keyboard = await _get_grades_text(
            student_id, period, token,
            profile_id=profile_id,
        )
        await callback.message.edit_text(
            text, reply_markup=keyboard, parse_mode="HTML"
        )
    except AuthenticationError:
        # Токен оказался недействительным — сбрасываем и пробуем получить новый
        logger.warning("Токен 401 для user_id=%d, пробуем переавторизацию", user_id)
        try:
            await invalidate_token(user_id)
            token = await ensure_token(user_id)
            text, keyboard = await _get_grades_text(
                student_id, period, token,
                profile_id=profile_id,
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
        logger.error("Ошибка API МЭШ для user_id=%d: %s", user_id, e)
        retry_keyboard = _get_retry_keyboard(student_id, period)
        await callback.message.edit_text(
            "\u26a0\ufe0f Сервис МЭШ временно недоступен, попробуйте позже",
            reply_markup=retry_keyboard
        )


# ============================================================================
# ОБРАБОТЧИК КОМАНДЫ /ocenki
# ============================================================================

@router.message(Command("ocenki"))
async def cmd_ocenki(message: Message):
    """Обработчик команды /ocenki — показ оценок."""
    user_id = message.from_user.id

    # Проверяем регистрацию
    user = await get_user(user_id)
    if not user:
        await message.answer(
            "Вы ещё не зарегистрированы.",
            reply_markup=_home_only_keyboard(),
        )
        return

    # Проверяем profile_id
    profile_id = user.get("mesh_profile_id")
    if not profile_id:
        await message.answer(
            "\u274c Для просмотра оценок необходимо перерегистрировать МЭШ-аккаунт.",
            reply_markup=_reregister_keyboard(),
        )
        return

    # Получаем список детей
    children = await get_user_children(user_id)
    if not children:
        await message.answer(
            "У вас нет привязанных детей.",
            reply_markup=_home_only_keyboard(),
        )
        return

    # Если несколько детей — показать кнопки выбора
    if len(children) > 1:
        keyboard = _get_child_keyboard(children)
        await message.answer(
            "Выберите ребёнка для просмотра оценок:",
            reply_markup=keyboard
        )
        return

    # Один ребёнок — сразу показать оценки за сегодня
    child = children[0]
    student_id = child["student_id"]

    try:
        token = await ensure_token(user_id)
    except AuthenticationError as e:
        logger.error("Ошибка авторизации МЭШ для user_id=%d: %s", user_id, e)
        await message.answer(
            f"\u274c {e}",
            reply_markup=_home_only_keyboard(),
        )
        return

    try:
        text, keyboard = await _get_grades_text(
            student_id, "today", token,
            profile_id=profile_id,
        )
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    except AuthenticationError:
        logger.warning("Токен 401 для user_id=%d, пробуем переавторизацию", user_id)
        try:
            await invalidate_token(user_id)
            token = await ensure_token(user_id)
            text, keyboard = await _get_grades_text(
                student_id, "today", token,
                profile_id=profile_id,
            )
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        except AuthenticationError as e2:
            logger.error("Повторная авторизация не помогла для user_id=%d: %s", user_id, e2)
            await message.answer(
                f"\u274c {e2}",
                reply_markup=_home_only_keyboard(),
            )
    except MeshAPIError as e:
        logger.error("Ошибка API МЭШ для user_id=%d: %s", user_id, e)
        retry_keyboard = _get_retry_keyboard(student_id, "today")
        await message.answer(
            "\u26a0\ufe0f Сервис МЭШ временно недоступен, попробуйте позже",
            reply_markup=retry_keyboard
        )


# ============================================================================
# ОБРАБОТЧИК КНОПКИ МЕНЮ
# ============================================================================

@router.callback_query(F.data == "menu:ocenki")
async def cb_menu_ocenki(callback: CallbackQuery):
    """Обработчик кнопки 'Оценки' из главного меню."""
    await callback.answer()
    user_id = callback.from_user.id

    user = await get_user(user_id)
    if not user:
        await callback.message.edit_text(
            "Вы ещё не зарегистрированы.",
            reply_markup=_home_only_keyboard(),
        )
        return

    profile_id = user.get("mesh_profile_id")
    if not profile_id:
        await callback.message.edit_text(
            "\u274c Для просмотра оценок необходимо перерегистрировать МЭШ-аккаунт.",
            reply_markup=_reregister_keyboard(),
        )
        return

    children = await get_user_children(user_id)
    if not children:
        await callback.message.edit_text(
            "У вас нет привязанных детей.",
            reply_markup=_home_only_keyboard(),
        )
        return

    if len(children) > 1:
        keyboard = _get_child_keyboard(children)
        await callback.message.edit_text(
            "Выберите ребёнка для просмотра оценок:",
            reply_markup=keyboard
        )
        return

    # Один ребёнок — сразу оценки за сегодня
    child = children[0]
    student_id = child["student_id"]
    await _handle_grades_request(callback, student_id, "today")


# ============================================================================
# ОБРАБОТЧИКИ CALLBACK
# ============================================================================

@router.callback_query(F.data.startswith("ocenki:child:"))
async def cb_select_child(callback: CallbackQuery):
    """Обработчик выбора ребёнка — показать оценки за сегодня."""
    await callback.answer()

    parsed = _parse_callback_data(callback.data)
    if parsed is None:
        logger.warning("Невалидный callback_data: %s", callback.data)
        return

    _, student_id, _ = parsed
    await _handle_grades_request(callback, student_id, "today")


@router.callback_query(F.data.startswith("ocenki:period:"))
async def cb_switch_period(callback: CallbackQuery):
    """Обработчик переключения периода (сегодня/неделя/месяц)."""
    await callback.answer()

    parsed = _parse_callback_data(callback.data)
    if parsed is None:
        logger.warning("Невалидный callback_data: %s", callback.data)
        return

    _, student_id, period = parsed

    if period not in ("today", "week", "month"):
        logger.warning("Неизвестный период в callback_data: %s", callback.data)
        return

    await _handle_grades_request(callback, student_id, period)


@router.callback_query(F.data.startswith("ocenki:retry:"))
async def cb_retry(callback: CallbackQuery):
    """Обработчик кнопки 'Повторить' после ошибки."""
    await callback.answer()

    parsed = _parse_callback_data(callback.data)
    if parsed is None:
        logger.warning("Невалидный callback_data: %s", callback.data)
        return

    _, student_id, period = parsed

    if period not in ("today", "week", "month"):
        logger.warning("Неизвестный период в callback_data: %s", callback.data)
        return

    await _handle_grades_request(callback, student_id, period)


# ============================================================================
# ОБРАБОТЧИК КНОПКИ «НАЗАД»
# ============================================================================

@router.callback_query(F.data == "ocenki:back")
async def cb_back(callback: CallbackQuery):
    """Назад: к выбору ребёнка (если >1) или в главное меню."""
    await callback.answer()
    user_id = callback.from_user.id

    children = await get_user_children(user_id)
    if len(children) > 1:
        keyboard = _get_child_keyboard(children)
        await callback.message.edit_text(
            "Выберите ребёнка для просмотра оценок:",
            reply_markup=keyboard,
        )
    else:
        from keyboards.main_menu import full_menu_keyboard, student_menu_keyboard
        role = await get_user_role(user_id)
        if role == "student":
            await callback.message.edit_text(
                "👋 Выбери, что хочешь сделать:",
                reply_markup=student_menu_keyboard(),
            )
        else:
            await callback.message.edit_text(
                "Главное меню:",
                reply_markup=full_menu_keyboard(),
            )
