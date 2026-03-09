"""Обработчик команды /dz — домашние задания из МЭШ."""
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
from mesh_api.models import Homework
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

# Лимиты
_MAX_MESSAGE_LEN = 3800
_MAX_ASSIGNMENT_LEN = 500
_DEFAULT_DZ_PERIOD = "tomorrow"


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def _next_school_day(base: date) -> date:
    """Возвращает следующий учебный день для 5-дневки."""
    wd = base.weekday()  # Mon=0 ... Sun=6
    if wd == 4:  # Friday -> Monday
        return base + timedelta(days=3)
    if wd == 5:  # Saturday -> Monday
        return base + timedelta(days=2)
    return base + timedelta(days=1)


def _get_period_dates(period: str) -> Tuple[date, date]:
    """Возвращает (from_date, to_date) для указанного периода (ДЗ смотрят вперёд)."""
    today = date.today()
    if period == "tomorrow":
        target = _next_school_day(today)
        return (target, target)
    elif period == "week":
        return (today, today + timedelta(days=6))
    else:  # default
        target = _next_school_day(today)
        return (target, target)


def _get_period_label(period: str) -> str:
    """Возвращает человекочитаемое название периода."""
    labels = {
        "today": "на сегодня",
        "tomorrow": "на завтра",
        "week": "на неделю",
    }
    return labels.get(period, "на завтра")


def _format_day_header(day_date: date) -> str:
    """Форматирует заголовок дня: '3 марта (вторник)'."""
    day_num = day_date.day
    month_name = _MONTH_NAMES[day_date.month]
    weekday_name = _WEEKDAY_NAMES[day_date.weekday()]
    return f"{day_num} {month_name} ({weekday_name})"


def _format_homework_item(hw: Homework) -> str:
    """Форматирует одно домашнее задание."""
    subject = html.escape(hw.subject)
    assignment = html.escape(hw.assignment)

    # Обрезаем длинный текст задания
    if len(assignment) > _MAX_ASSIGNMENT_LEN:
        assignment = assignment[:_MAX_ASSIGNMENT_LEN - 3] + "..."

    return f"\U0001f4da {subject}:\n   {assignment}"


def _format_homework(homework_list: List[Homework], period: str) -> str:
    """Форматирует полное сообщение с домашними заданиями."""
    label = _get_period_label(period)
    header = f"<b>\U0001f4dd Домашние задания {label}</b>\n"

    if not homework_list:
        return f"{header}\n\U0001f4ed На выбранный период заданий нет"

    # Группировка по дате (ближайшие сверху)
    by_date = defaultdict(list)
    for hw in homework_list:
        by_date[hw.due_date].append(hw)

    sorted_dates = sorted(by_date.keys())

    lines = [header]
    total_items = 0
    truncated = False

    for day_date in sorted_dates:
        day_header = f"\n<b>{_format_day_header(day_date)}</b>"
        day_lines = [day_header]

        for hw in by_date[day_date]:
            day_lines.append("")
            day_lines.append(_format_homework_item(hw))

        day_block = "\n".join(day_lines)

        # Проверка длины
        current_len = len("\n".join(lines))
        if current_len + len(day_block) > _MAX_MESSAGE_LEN:
            remaining = sum(len(by_date[d]) for d in sorted_dates) - total_items
            lines.append(f"\n... и ещё {remaining} заданий")
            truncated = True
            break

        lines.append(day_block)
        total_items += len(by_date[day_date])

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
                callback_data=f"dz:period:{student_id}:today"
            ),
            InlineKeyboardButton(
                text="\U0001f4c5 Завтра",
                callback_data=f"dz:period:{student_id}:tomorrow"
            ),
            InlineKeyboardButton(
                text="\U0001f4c5 Неделя",
                callback_data=f"dz:period:{student_id}:week"
            ),
        ],
        [back_button("dz:back"), home_button()],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _get_retry_keyboard(student_id: int, period: str) -> InlineKeyboardMarkup:
    """Кнопка повторной попытки после ошибки."""
    buttons = [
        [
            InlineKeyboardButton(
                text="\U0001f504 Повторить",
                callback_data=f"dz:retry:{student_id}:{period}"
            )
        ],
        [back_button("dz:back"), home_button()],
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
                callback_data=f"dz:child:{child['student_id']}"
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
    Парсит callback_data формата dz:action:student_id[:extra].

    Returns:
        Tuple (action, student_id, extra) или None при ошибке.
    """
    try:
        parts = data.split(":")
        if len(parts) < 3 or parts[0] != "dz":
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

async def _get_homework_text(
    student_id: int, period: str, token: str,
    profile_id: Optional[int] = None,
) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Получает текст домашних заданий и клавиатуру для указанного периода.

    Returns:
        Tuple (текст_сообщения, клавиатура)

    Raises:
        AuthenticationError: Проблема с авторизацией
        MeshAPIError: Ошибка API
    """
    from_date, to_date = _get_period_dates(period)

    client = MeshClient()
    try:
        homework_list = await client.get_homework(
            student_id=student_id,
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
            token=token,
            profile_id=profile_id,
        )
    finally:
        await client.close()

    text = _format_homework(homework_list, period)
    keyboard = _get_period_keyboard(student_id)
    return text, keyboard


# ============================================================================
# ОБЩАЯ ЛОГИКА CALLBACK-ОБРАБОТЧИКОВ
# ============================================================================

async def _handle_homework_request(
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

    # Получаем profile_id пользователя (нужен для API ДЗ)
    user = await get_user(user_id)
    profile_id = user.get("mesh_profile_id") if user else None

    if not profile_id:
        await callback.message.edit_text(
            "\u274c Для просмотра ДЗ необходимо перерегистрировать МЭШ-аккаунт.",
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
        text, keyboard = await _get_homework_text(
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
            text, keyboard = await _get_homework_text(
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
# ОБРАБОТЧИК КОМАНДЫ /dz
# ============================================================================

@router.message(Command("dz"))
async def cmd_dz(message: Message):
    """Обработчик команды /dz — показ домашних заданий."""
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
            "\u274c Для просмотра ДЗ необходимо перерегистрировать МЭШ-аккаунт.",
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
            "Выберите ребёнка для просмотра домашних заданий:",
            reply_markup=keyboard
        )
        return

    # Один ребёнок — сразу показать ДЗ на завтра
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
        text, keyboard = await _get_homework_text(
            student_id, _DEFAULT_DZ_PERIOD, token,
            profile_id=profile_id,
        )
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    except AuthenticationError:
        logger.warning("Токен 401 для user_id=%d, пробуем переавторизацию", user_id)
        try:
            await invalidate_token(user_id)
            token = await ensure_token(user_id)
            text, keyboard = await _get_homework_text(
                student_id, _DEFAULT_DZ_PERIOD, token,
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
        retry_keyboard = _get_retry_keyboard(student_id, _DEFAULT_DZ_PERIOD)
        await message.answer(
            "\u26a0\ufe0f Сервис МЭШ временно недоступен, попробуйте позже",
            reply_markup=retry_keyboard
        )


# ============================================================================
# ОБРАБОТЧИК КНОПКИ МЕНЮ
# ============================================================================

@router.callback_query(F.data == "menu:dz")
async def cb_menu_dz(callback: CallbackQuery):
    """Обработчик кнопки 'Домашние задания' из главного меню."""
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
            "\u274c Для просмотра ДЗ необходимо перерегистрировать МЭШ-аккаунт.",
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
            "Выберите ребёнка для просмотра домашних заданий:",
            reply_markup=keyboard
        )
        return

    # Один ребёнок — сразу ДЗ на завтра
    child = children[0]
    student_id = child["student_id"]
    await _handle_homework_request(callback, student_id, _DEFAULT_DZ_PERIOD)


# ============================================================================
# ОБРАБОТЧИКИ CALLBACK
# ============================================================================

@router.callback_query(F.data.startswith("dz:child:"))
async def cb_select_child(callback: CallbackQuery):
    """Обработчик выбора ребёнка — показать ДЗ на завтра."""
    await callback.answer()

    parsed = _parse_callback_data(callback.data)
    if parsed is None:
        logger.warning("Невалидный callback_data: %s", callback.data)
        return

    _, student_id, _ = parsed
    await _handle_homework_request(callback, student_id, _DEFAULT_DZ_PERIOD)


@router.callback_query(F.data.startswith("dz:period:"))
async def cb_switch_period(callback: CallbackQuery):
    """Обработчик переключения периода (сегодня/завтра/неделя)."""
    await callback.answer()

    parsed = _parse_callback_data(callback.data)
    if parsed is None:
        logger.warning("Невалидный callback_data: %s", callback.data)
        return

    _, student_id, period = parsed

    if period not in ("today", "tomorrow", "week"):
        logger.warning("Неизвестный период в callback_data: %s", callback.data)
        return

    await _handle_homework_request(callback, student_id, period)


@router.callback_query(F.data.startswith("dz:retry:"))
async def cb_retry(callback: CallbackQuery):
    """Обработчик кнопки 'Повторить' после ошибки."""
    await callback.answer()

    parsed = _parse_callback_data(callback.data)
    if parsed is None:
        logger.warning("Невалидный callback_data: %s", callback.data)
        return

    _, student_id, period = parsed

    if period not in ("today", "tomorrow", "week"):
        logger.warning("Неизвестный период в callback_data: %s", callback.data)
        return

    await _handle_homework_request(callback, student_id, period)


# ============================================================================
# ОБРАБОТЧИК КНОПКИ «НАЗАД»
# ============================================================================

@router.callback_query(F.data == "dz:back")
async def cb_back(callback: CallbackQuery):
    """Назад: к выбору ребёнка (если >1) или в главное меню."""
    await callback.answer()
    user_id = callback.from_user.id

    children = await get_user_children(user_id)
    if len(children) > 1:
        keyboard = _get_child_keyboard(children)
        await callback.message.edit_text(
            "Выберите ребёнка для просмотра ДЗ:",
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
