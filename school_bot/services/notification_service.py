"""Сервис уведомлений: проверка новых оценок/ДЗ, отправка через Telegram."""
import asyncio
import html
import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from config import settings
from database.crud import (
    get_users_with_notifications,
    get_user_children,
    get_user,
    cache_new_grades,
    get_unnotified_grades,
    mark_grades_notified,
    cache_new_homework,
    get_unnotified_homework,
    mark_homework_notified,
    disable_all_notifications,
    cleanup_old_cache,
    log_activity,
)
from mesh_api.client import MeshClient
from mesh_api.exceptions import AuthenticationError, MeshAPIError
from utils.token_manager import ensure_token

logger = logging.getLogger(__name__)

# Глобальная ссылка на bot (инициализируется в init_scheduler)
_bot: Optional[Bot] = None

# Пауза между запросами к МЭШ API (rate limit: 30/мин)
_API_DELAY_SEC = 2.5


def init_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Создать и настроить планировщик уведомлений."""
    global _bot
    _bot = bot

    tz = pytz.timezone(settings.TIMEZONE)
    scheduler = AsyncIOScheduler(timezone=tz)

    # Парсим время из настроек
    grades_h, grades_m = settings.GRADES_NOTIFICATION_TIME.split(":")
    hw_h, hw_m = settings.HOMEWORK_NOTIFICATION_TIME.split(":")

    # Оценки — ежедневно
    scheduler.add_job(
        _send_grades_notifications,
        CronTrigger(hour=int(grades_h), minute=int(grades_m), timezone=tz),
        id="daily_grades",
        replace_existing=True,
    )

    # ДЗ — ежедневно
    scheduler.add_job(
        _send_homework_notifications,
        CronTrigger(hour=int(hw_h), minute=int(hw_m), timezone=tz),
        id="daily_homework",
        replace_existing=True,
    )

    # Очистка старого кеша — раз в неделю, ночью
    scheduler.add_job(
        _cleanup_cache_job,
        CronTrigger(day_of_week="sun", hour=3, minute=0, timezone=tz),
        id="weekly_cache_cleanup",
        replace_existing=True,
    )

    return scheduler


# ============================================================================
# ОЦЕНКИ
# ============================================================================

async def _send_grades_notifications():
    """Задача планировщика: проверить новые оценки и отправить уведомления."""
    logger.info("Уведомления: запуск проверки новых оценок...")

    subscribers = await get_users_with_notifications("grades")
    if not subscribers:
        logger.info("Уведомления: нет подписчиков на оценки")
        return

    # Группируем по user_id
    by_user = defaultdict(list)
    for sub in subscribers:
        by_user[sub["user_id"]].append(sub)

    sent_count = 0
    error_count = 0

    for user_id, subs in by_user.items():
        try:
            await _process_grades_for_user(user_id, subs)
            sent_count += 1
        except Exception as e:
            logger.error("Уведомления: ошибка оценок для user_id=%d: %s", user_id, e)
            error_count += 1

        await asyncio.sleep(_API_DELAY_SEC)

    logger.info("Уведомления: оценки — обработано %d, ошибок %d", sent_count, error_count)


async def _process_grades_for_user(user_id: int, subs: list):
    """Обработать уведомления об оценках для одного пользователя."""
    try:
        token = await ensure_token(user_id)
    except Exception as e:
        logger.warning("Уведомления: не удалось получить токен для user_id=%d: %s", user_id, e)
        return

    if not token:
        return

    user = await get_user(user_id)
    profile_id = user.get("mesh_profile_id") if user else None
    if not profile_id:
        return

    children = await get_user_children(user_id)
    if not children:
        return

    today = date.today()
    all_new_grades = []

    for child in children:
        client = MeshClient()
        try:
            grades = await client.get_grades(
                student_id=child["student_id"],
                from_date=today.isoformat(),
                to_date=today.isoformat(),
                token=token,
                profile_id=profile_id,
            )
        except (AuthenticationError, MeshAPIError) as e:
            logger.warning("Уведомления: ошибка МЭШ API для child %d: %s", child["student_id"], e)
            continue
        finally:
            await client.close()

        if not grades:
            continue

        # Конвертируем Grade dataclass в dict для кеша
        grade_dicts = [
            {
                "subject": g.subject,
                "grade_value": g.grade_value,
                "date": g.date,
                "lesson_type": g.lesson_type,
                "teacher": g.teacher,
                "comment": g.comment,
            }
            for g in grades
        ]

        new_count = await cache_new_grades(child["child_id"], grade_dicts)
        if new_count > 0:
            unnotified = await get_unnotified_grades(child["child_id"])
            child_name = f"{child['first_name']} {child['last_name']}"
            all_new_grades.append((child_name, unnotified))

        await asyncio.sleep(_API_DELAY_SEC)

    # Отправляем уведомление
    if all_new_grades:
        text = _format_grades_notification(all_new_grades)
        await _safe_send_message(user_id, text)

        # Помечаем отправленными
        for _, grades in all_new_grades:
            ids = [g["grade_id"] for g in grades]
            await mark_grades_notified(ids)

        total = sum(len(g) for _, g in all_new_grades)
        await log_activity(user_id, "notification_sent", f"grades: {total} new")


# ============================================================================
# ДОМАШНИЕ ЗАДАНИЯ
# ============================================================================

async def _send_homework_notifications():
    """Задача планировщика: проверить новые ДЗ и отправить уведомления."""
    logger.info("Уведомления: запуск проверки новых ДЗ...")

    subscribers = await get_users_with_notifications("homework")
    if not subscribers:
        logger.info("Уведомления: нет подписчиков на ДЗ")
        return

    by_user = defaultdict(list)
    for sub in subscribers:
        by_user[sub["user_id"]].append(sub)

    sent_count = 0
    error_count = 0

    for user_id, subs in by_user.items():
        try:
            await _process_homework_for_user(user_id, subs)
            sent_count += 1
        except Exception as e:
            logger.error("Уведомления: ошибка ДЗ для user_id=%d: %s", user_id, e)
            error_count += 1

        await asyncio.sleep(_API_DELAY_SEC)

    logger.info("Уведомления: ДЗ — обработано %d, ошибок %d", sent_count, error_count)


async def _process_homework_for_user(user_id: int, subs: list):
    """Обработать уведомления о ДЗ для одного пользователя."""
    try:
        token = await ensure_token(user_id)
    except Exception:
        return

    if not token:
        return

    user = await get_user(user_id)
    profile_id = user.get("mesh_profile_id") if user else None
    if not profile_id:
        return

    children = await get_user_children(user_id)
    if not children:
        return

    today = date.today()
    tomorrow = today + timedelta(days=1)
    all_new_hw = []

    for child in children:
        client = MeshClient()
        try:
            homework_list = await client.get_homework(
                student_id=child["student_id"],
                from_date=tomorrow.isoformat(),
                to_date=(tomorrow + timedelta(days=6)).isoformat(),
                token=token,
                profile_id=profile_id,
            )
        except (AuthenticationError, MeshAPIError):
            continue
        finally:
            await client.close()

        if not homework_list:
            continue

        hw_dicts = [
            {
                "subject": hw.subject,
                "assignment": hw.assignment,
                "due_date": hw.due_date,
            }
            for hw in homework_list
        ]

        new_count = await cache_new_homework(child["child_id"], hw_dicts)
        if new_count > 0:
            unnotified = await get_unnotified_homework(child["child_id"])
            child_name = f"{child['first_name']} {child['last_name']}"
            all_new_hw.append((child_name, unnotified))

        await asyncio.sleep(_API_DELAY_SEC)

    if all_new_hw:
        text = _format_homework_notification(all_new_hw)
        await _safe_send_message(user_id, text)

        for _, hw_list in all_new_hw:
            ids = [hw["homework_id"] for hw in hw_list]
            await mark_homework_notified(ids)

        total = sum(len(h) for _, h in all_new_hw)
        await log_activity(user_id, "notification_sent", f"homework: {total} new")


# ============================================================================
# ФОРМАТИРОВАНИЕ
# ============================================================================

def _format_grades_notification(all_new_grades: list) -> str:
    """Форматирует уведомление о новых оценках в HTML."""
    lines = ["<b>Новые оценки за сегодня</b>\n"]

    for child_name, grades in all_new_grades:
        if len(all_new_grades) > 1:
            lines.append(f"\n<b>{html.escape(child_name)}</b>")

        for g in grades:
            subject = html.escape(g["subject"])
            value = html.escape(str(g["grade_value"]))
            line = f"  {subject} — <b>{value}</b>"
            if g.get("lesson_type"):
                line += f" ({html.escape(g['lesson_type'])})"
            lines.append(line)

    return "\n".join(lines)


def _format_homework_notification(all_new_hw: list) -> str:
    """Форматирует уведомление о новых ДЗ в HTML."""
    lines = ["<b>Новые домашние задания</b>\n"]

    for child_name, hw_list in all_new_hw:
        if len(all_new_hw) > 1:
            lines.append(f"\n<b>{html.escape(child_name)}</b>")

        for hw in hw_list:
            subject = html.escape(hw["subject"])
            assignment = html.escape(hw["assignment"] or "—")
            if len(assignment) > 200:
                assignment = assignment[:197] + "..."
            lines.append(f"  {subject}: {assignment}")

    return "\n".join(lines)


# ============================================================================
# ОТПРАВКА
# ============================================================================

async def _safe_send_message(user_id: int, text: str):
    """Отправить сообщение с обработкой ошибок Telegram."""
    if not _bot:
        logger.error("Уведомления: bot не инициализирован")
        return

    try:
        await _bot.send_message(user_id, text, parse_mode="HTML")
    except TelegramForbiddenError:
        logger.warning("Уведомления: бот заблокирован user_id=%d, отключаю уведомления", user_id)
        await disable_all_notifications(user_id)
    except TelegramBadRequest as e:
        logger.error("Уведомления: ошибка отправки user_id=%d: %s", user_id, e)
    except Exception as e:
        logger.error("Уведомления: неизвестная ошибка user_id=%d: %s", user_id, e)


# ============================================================================
# ОЧИСТКА КЕША
# ============================================================================

async def _cleanup_cache_job():
    """Еженедельная очистка старого кеша."""
    logger.info("Уведомления: очистка кеша старше 30 дней...")
    await cleanup_old_cache(30)
    logger.info("Уведомления: очистка кеша завершена")
