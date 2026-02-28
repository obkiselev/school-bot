"""Обработчик команды /raspisanie — расписание уроков из МЭШ."""
import html
import logging
from datetime import date, timedelta
from typing import List, Optional, Tuple

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database.crud import get_user, get_user_children
from mesh_api.client import MeshClient
from mesh_api.exceptions import AuthenticationError, MeshAPIError
from mesh_api.models import Lesson
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


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def _get_week_dates(today: date) -> List[date]:
    """Возвращает даты Пн-Пт текущей недели."""
    monday = today - timedelta(days=today.weekday())
    return [monday + timedelta(days=i) for i in range(5)]


def _format_day_header(day_date: date) -> str:
    """Форматирует заголовок дня: '27 февраля (четверг)'."""
    day_num = day_date.day
    month_name = _MONTH_NAMES[day_date.month]
    weekday_name = _WEEKDAY_NAMES[day_date.weekday()]
    return f"{day_num} {month_name} ({weekday_name})"


def _format_day_schedule(day_date: date, lessons: List[Lesson]) -> str:
    """Форматирует расписание одного дня."""
    header = _format_day_header(day_date)

    if not lessons:
        return f"<b>\U0001f4da Расписание на {header}</b>\n\n\U0001f4ed На этот день уроков нет"

    lines = [f"<b>\U0001f4da Расписание на {header}</b>\n"]

    for lesson in lessons:
        # Основная строка: номер, время, предмет (экранируем данные от API)
        line = (
            f"{lesson.number}. "
            f"{html.escape(lesson.time_start)}\u2013{html.escape(lesson.time_end)} "
            f"\u2014 {html.escape(lesson.subject)}"
        )
        lines.append(line)

        # Дополнительная строка: кабинет и учитель
        details = []
        if lesson.room:
            details.append(f"\U0001f4cd Каб. {html.escape(lesson.room)}")
        if lesson.teacher:
            details.append(f"\U0001f468\u200d\U0001f3eb {html.escape(lesson.teacher)}")

        if details:
            lines.append(f"   {' | '.join(details)}")

        # Пустая строка между уроками
        lines.append("")

    return "\n".join(lines).rstrip()


def _format_week_schedule(results: List[Tuple[date, Optional[List[Lesson]]]]) -> Optional[str]:
    """Форматирует расписание на неделю."""
    parts = []
    has_any_data = False

    for day_date, lessons in results:
        if lessons is None:
            # Ошибка загрузки этого дня
            header = _format_day_header(day_date)
            parts.append(f"<b>\u26a0\ufe0f {header}</b>\n   Не удалось загрузить\n")
        else:
            has_any_data = True
            parts.append(_format_day_schedule(day_date, lessons))
            parts.append("")  # Разделитель между днями

    if not has_any_data:
        return None  # Все дни упали — вернём None для общей ошибки

    return "\n".join(parts).rstrip()


def _get_period_keyboard(student_id: int) -> InlineKeyboardMarkup:
    """Кнопки переключения периода."""
    buttons = [
        [
            InlineKeyboardButton(
                text="\U0001f4c5 Сегодня",
                callback_data=f"sched:period:{student_id}:today"
            ),
            InlineKeyboardButton(
                text="\U0001f4c5 Завтра",
                callback_data=f"sched:period:{student_id}:tomorrow"
            ),
            InlineKeyboardButton(
                text="\U0001f4c5 Неделя",
                callback_data=f"sched:period:{student_id}:week"
            ),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _get_retry_keyboard(student_id: int, period: str) -> InlineKeyboardMarkup:
    """Кнопка повторной попытки после ошибки."""
    buttons = [
        [
            InlineKeyboardButton(
                text="\U0001f504 Повторить",
                callback_data=f"sched:retry:{student_id}:{period}"
            )
        ]
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
                callback_data=f"sched:child:{child['student_id']}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _parse_callback_data(data: str) -> Optional[tuple]:
    """
    Парсит callback_data формата sched:action:student_id[:extra].

    Returns:
        Tuple (action, student_id, extra) или None при ошибке.
        extra может быть None если не указан.
    """
    try:
        parts = data.split(":")
        if len(parts) < 3 or parts[0] != "sched":
            return None

        action = parts[1]
        student_id = int(parts[2])
        extra = parts[3] if len(parts) > 3 else None

        return (action, student_id, extra)
    except (ValueError, IndexError):
        return None


async def _fetch_week_schedule(
    client: MeshClient, student_id: int, today: date, token: str
) -> Optional[str]:
    """
    Получает расписание на неделю (Пн-Пт).
    Каждый день в отдельном try/except.
    AuthenticationError пробрасывается наверх — не маскируется.

    Returns:
        Отформатированный текст или None если все дни упали.

    Raises:
        AuthenticationError: Проблема с авторизацией (пробрасывается сразу)
    """
    week_dates = _get_week_dates(today)
    results: List[Tuple[date, Optional[List[Lesson]]]] = []

    for day_date in week_dates:
        try:
            lessons = await client.get_schedule(student_id, day_date.isoformat(), token)
            results.append((day_date, lessons))
        except AuthenticationError:
            raise  # Не маскируем — пусть вызывающий покажет "перерегистрируйтесь"
        except MeshAPIError as e:
            logger.error(
                "Ошибка загрузки расписания на %s для student_id=%d: %s",
                day_date.isoformat(), student_id, e
            )
            results.append((day_date, None))  # Пропускаем этот день

    return _format_week_schedule(results)


async def _get_schedule_text(
    student_id: int, period: str, token: str
) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Получает текст расписания и клавиатуру для указанного периода.

    Returns:
        Tuple (текст_сообщения, клавиатура)

    Raises:
        AuthenticationError: Проблема с авторизацией
        MeshAPIError: Ошибка API
    """
    today = date.today()

    client = MeshClient()
    try:
        if period == "today":
            lessons = await client.get_schedule(student_id, today.isoformat(), token)
            text = _format_day_schedule(today, lessons)
        elif period == "tomorrow":
            tomorrow = today + timedelta(days=1)
            lessons = await client.get_schedule(student_id, tomorrow.isoformat(), token)
            text = _format_day_schedule(tomorrow, lessons)
        elif period == "week":
            week_text = await _fetch_week_schedule(client, student_id, today, token)
            if week_text is None:
                # Все 5 дней упали — бросаем общую ошибку
                raise MeshAPIError("Не удалось загрузить расписание на неделю")
            text = week_text
        else:
            # Неизвестный период — по умолчанию сегодня
            lessons = await client.get_schedule(student_id, today.isoformat(), token)
            text = _format_day_schedule(today, lessons)
    finally:
        await client.close()

    keyboard = _get_period_keyboard(student_id)
    return text, keyboard


# ============================================================================
# ОБЩАЯ ЛОГИКА CALLBACK-ОБРАБОТЧИКОВ
# ============================================================================

async def _handle_schedule_request(
    callback: CallbackQuery,
    student_id: int,
    period: str
) -> None:
    """Общая логика: IDOR check -> token -> fetch -> format -> edit message."""
    user_id = callback.from_user.id

    # IDOR-проверка: ребёнок принадлежит пользователю
    children = await get_user_children(user_id)
    child_ids = [c["student_id"] for c in children]
    if student_id not in child_ids:
        logger.warning("Попытка IDOR: user %d запросил student %d", user_id, student_id)
        return

    # Получаем токен
    try:
        token = await ensure_token(user_id)
    except AuthenticationError:
        await callback.message.edit_text(
            "\u274c Не удалось подключиться к МЭШ. "
            "Пожалуйста, перерегистрируйтесь: /start"
        )
        return

    # Получаем расписание
    try:
        text, keyboard = await _get_schedule_text(student_id, period, token)
        await callback.message.edit_text(
            text, reply_markup=keyboard, parse_mode="HTML"
        )
    except AuthenticationError:
        logger.error("Ошибка авторизации МЭШ для user_id=%d", user_id)
        await callback.message.edit_text(
            "\u274c Не удалось подключиться к МЭШ. "
            "Пожалуйста, перерегистрируйтесь: /start"
        )
    except MeshAPIError as e:
        logger.error("Ошибка API МЭШ для user_id=%d: %s", user_id, e)
        retry_keyboard = _get_retry_keyboard(student_id, period)
        await callback.message.edit_text(
            "\u26a0\ufe0f Сервис МЭШ временно недоступен, попробуйте позже",
            reply_markup=retry_keyboard
        )


# ============================================================================
# ОБРАБОТЧИК КОМАНДЫ /raspisanie
# ============================================================================

@router.message(Command("raspisanie"))
async def cmd_raspisanie(message: Message):
    """Обработчик команды /raspisanie — показ расписания уроков."""
    user_id = message.from_user.id

    # Проверяем регистрацию
    user = await get_user(user_id)
    if not user:
        await message.answer(
            "Вы ещё не зарегистрированы. Сначала зарегистрируйтесь: /start"
        )
        return

    # Получаем список детей
    children = await get_user_children(user_id)
    if not children:
        await message.answer(
            "У вас нет привязанных детей. Пройдите регистрацию: /start"
        )
        return

    # Если несколько детей — показать кнопки выбора
    if len(children) > 1:
        keyboard = _get_child_keyboard(children)
        await message.answer(
            "Выберите ребёнка для просмотра расписания:",
            reply_markup=keyboard
        )
        return

    # Один ребёнок — сразу показать расписание на сегодня
    student_id = children[0]["student_id"]

    # Получаем токен
    try:
        token = await ensure_token(user_id)
    except AuthenticationError:
        await message.answer(
            "\u274c Не удалось подключиться к МЭШ. "
            "Пожалуйста, перерегистрируйтесь: /start"
        )
        return

    # Получаем расписание
    try:
        text, keyboard = await _get_schedule_text(student_id, "today", token)
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    except AuthenticationError:
        logger.error("Ошибка авторизации МЭШ для user_id=%d", user_id)
        await message.answer(
            "\u274c Не удалось подключиться к МЭШ. "
            "Пожалуйста, перерегистрируйтесь: /start"
        )
    except MeshAPIError as e:
        logger.error("Ошибка API МЭШ для user_id=%d: %s", user_id, e)
        retry_keyboard = _get_retry_keyboard(student_id, "today")
        await message.answer(
            "\u26a0\ufe0f Сервис МЭШ временно недоступен, попробуйте позже",
            reply_markup=retry_keyboard
        )


# ============================================================================
# ОБРАБОТЧИКИ CALLBACK
# ============================================================================

@router.callback_query(F.data.startswith("sched:child:"))
async def cb_select_child(callback: CallbackQuery):
    """Обработчик выбора ребёнка — показать расписание на сегодня."""
    try:
        parsed = _parse_callback_data(callback.data)
        if parsed is None:
            logger.warning("Невалидный callback_data: %s", callback.data)
            return

        _, student_id, _ = parsed
        await _handle_schedule_request(callback, student_id, "today")
    finally:
        await callback.answer()


@router.callback_query(F.data.startswith("sched:period:"))
async def cb_switch_period(callback: CallbackQuery):
    """Обработчик переключения периода (сегодня/завтра/неделя)."""
    try:
        parsed = _parse_callback_data(callback.data)
        if parsed is None:
            logger.warning("Невалидный callback_data: %s", callback.data)
            return

        _, student_id, period = parsed

        if period not in ("today", "tomorrow", "week"):
            logger.warning("Неизвестный период в callback_data: %s", callback.data)
            return

        await _handle_schedule_request(callback, student_id, period)
    finally:
        await callback.answer()


@router.callback_query(F.data.startswith("sched:retry:"))
async def cb_retry(callback: CallbackQuery):
    """Обработчик кнопки 'Повторить' после ошибки."""
    try:
        parsed = _parse_callback_data(callback.data)
        if parsed is None:
            logger.warning("Невалидный callback_data: %s", callback.data)
            return

        _, student_id, period = parsed

        if period not in ("today", "tomorrow", "week"):
            logger.warning("Неизвестный период в callback_data: %s", callback.data)
            return

        await _handle_schedule_request(callback, student_id, period)
    finally:
        await callback.answer()
