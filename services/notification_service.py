"""Сервис уведомлений: проверка новых оценок/ДЗ, отправка через Telegram."""
import asyncio
import html
import logging
from dataclasses import dataclass
from collections import defaultdict
from datetime import date, timedelta
from datetime import datetime, time as dt_time
from typing import Optional, Literal, Union

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
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
    get_unnotified_homework_for_date,
    mark_homework_notified,
    was_homework_summary_sent,
    mark_homework_summary_sent,
    disable_all_notifications,
    cleanup_old_cache,
    log_activity,
    save_notification_run,
    get_last_notification_run,
    get_due_custom_reminders,
    mark_custom_reminder_sent,
)
from mesh_api.client import MeshClient
from mesh_api.exceptions import AuthenticationError, MeshAPIError
from utils.token_manager import ensure_token

logger = logging.getLogger(__name__)

ProcessStatus = Literal["sent", "no_changes", "failed"]


@dataclass
class ProcessResult:
    """Результат обработки уведомления для одного пользователя."""
    status: ProcessStatus
    retryable: bool = False
    api_calls: int = 0
    api_errors: int = 0
    error: Optional[str] = None

# Глобальная ссылка на bot (инициализируется в init_scheduler)
_bot: Optional[Bot] = None

# Retry-очередь для временных сбоев отправки/МЭШ API
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY_SEC = 120
_RETRY_JOB_INTERVAL_MIN = 5
_retry_queue: dict[tuple[int, str], dict] = {}

# Детектор длительной недоступности МЭШ API
_OUTAGE_RATIO_THRESHOLD = 0.8
_OUTAGE_MIN_API_CALLS = 3
_OUTAGE_RUNS_FOR_ALERT = 2
_OUTAGE_ALERT_COOLDOWN_SEC = 6 * 60 * 60
_outage_state = {
    "grades": {"consecutive": 0, "last_alert_at": None},
    "homework": {"consecutive": 0, "last_alert_at": None},
}

_HOMEWORK_SEND_DELAY_MIN = 30

_CONTROL_LESSON_KEYWORDS = (
    "контроль",
    "провероч",
    "самостоятель",
    "диктант",
    "тест",
    "экзамен",
    "зачет",
)


def _next_school_day(base: date) -> date:
    """Возвращает следующий учебный день для 5-дневки."""
    wd = base.weekday()  # Mon=0 ... Sun=6
    if wd == 4:  # Friday -> Monday
        return base + timedelta(days=3)
    if wd == 5:  # Saturday -> Monday
        return base + timedelta(days=2)
    return base + timedelta(days=1)

def init_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Создать и настроить планировщик уведомлений."""
    global _bot
    _bot = bot

    tz = pytz.timezone(settings.TIMEZONE)
    scheduler = AsyncIOScheduler(timezone=tz)

    # Парсим время из настроек
    grades_h, grades_m = settings.GRADES_NOTIFICATION_TIME.split(":")

    # Оценки — ежедневно
    scheduler.add_job(
        _send_grades_notifications,
        CronTrigger(hour=int(grades_h), minute=int(grades_m), timezone=tz),
        id="daily_grades",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )

    # ДЗ — периодическая проверка; фактическая отправка для student
    # открывается через 30 минут после окончания последнего урока.
    scheduler.add_job(
        _send_homework_notifications,
        CronTrigger(minute="*", timezone=tz),
        id="daily_homework",
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    # Напоминания-планировщик (контрольные + ДЗ на завтра)
    planner_h, planner_m = settings.REMINDER_NOTIFICATION_TIME.split(":")
    scheduler.add_job(
        _send_planner_reminders,
        CronTrigger(hour=int(planner_h), minute=int(planner_m), timezone=tz),
        id="daily_planner_reminders",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Очистка старого кеша — раз в неделю, ночью
    scheduler.add_job(
        _cleanup_cache_job,
        CronTrigger(day_of_week="sun", hour=3, minute=0, timezone=tz),
        id="weekly_cache_cleanup",
        replace_existing=True,
    )

    # Retry-очередь временных сбоев (МЭШ API/Telegram)
    scheduler.add_job(
        _process_retry_queue,
        IntervalTrigger(minutes=_RETRY_JOB_INTERVAL_MIN, timezone=tz),
        id="retry_queue_processor",
        replace_existing=True,
    )

    # Пользовательские напоминания (/remind) — проверка каждую минуту
    scheduler.add_job(
        _process_custom_reminders,
        IntervalTrigger(minutes=1, timezone=tz),
        id="custom_reminders_processor",
        replace_existing=True,
        coalesce=True,
    )

    # Очистка устаревших записей кеша при старте
    # (если бот был выключен, is_notified=0 записи — уже неактуальны)
    scheduler.add_job(
        _cleanup_stale_cache_on_start,
        "date",  # одноразовый запуск
        id="startup_cache_cleanup",
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

    total_users = len(by_user)
    sent_count = 0
    skipped_count = 0
    error_count = 0
    api_calls_total = 0
    api_errors_total = 0

    for user_id, subs in by_user.items():
        try:
            result = await _process_grades_for_user(user_id, subs)
            api_calls_total += result.api_calls
            api_errors_total += result.api_errors

            if result.status == "sent":
                sent_count += 1
            elif result.status == "failed":
                error_count += 1
                if result.retryable:
                    _enqueue_retry(user_id, "grades", result.error)
            else:
                skipped_count += 1
        except Exception as e:
            logger.error("Уведомления: ошибка оценок для user_id=%d: %s", user_id, e)
            error_count += 1
            _enqueue_retry(user_id, "grades", str(e))

    logger.info(
        "Уведомления: оценки — отправлено %d из %d, без изменений: %d, ошибок: %d",
        sent_count,
        total_users,
        skipped_count,
        error_count,
    )
    await _handle_outage_state("grades", api_calls_total, api_errors_total)
    await save_notification_run("grades", date.today())


async def _process_grades_for_user(user_id: int, subs: list) -> ProcessResult:
    """Обработать уведомления об оценках для одного пользователя."""
    api_calls = 0
    api_errors = 0

    try:
        token = await ensure_token(user_id)
    except Exception as e:
        logger.warning("Уведомления: не удалось получить токен для user_id=%d: %s", user_id, e)
        return ProcessResult("failed", retryable=True, error=f"token_error: {e}")

    if not token:
        logger.warning("Уведомления: пустой токен для user_id=%d", user_id)
        return ProcessResult("failed", retryable=False, error="empty_token")

    user = await get_user(user_id)
    profile_id = user.get("mesh_profile_id") if user else None
    if not profile_id:
        logger.warning("Уведомления: отсутствует profile_id для user_id=%d", user_id)
        return ProcessResult("failed", retryable=False, error="missing_profile_id")

    children = await get_user_children(user_id)
    if not children:
        logger.warning("Уведомления: не найдены дети для user_id=%d", user_id)
        return ProcessResult("failed", retryable=False, error="missing_children")

    today = date.today()
    all_new_grades = []

    for child in children:
        client = MeshClient()
        try:
            api_calls += 1
            grades = await client.get_grades(
                student_id=child["student_id"],
                from_date=today.isoformat(),
                to_date=today.isoformat(),
                token=token,
                profile_id=profile_id,
            )
        except (AuthenticationError, MeshAPIError) as e:
            api_errors += 1
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


    # Отправляем уведомление
    if all_new_grades:
        text = _format_grades_notification(all_new_grades)
        sent_ok = await _safe_send_message(user_id, text)

        if sent_ok:
            for _, grades in all_new_grades:
                ids = [g["grade_id"] for g in grades]
                await mark_grades_notified(ids)

            total = sum(len(g) for _, g in all_new_grades)
            await log_activity(user_id, "notification_sent", f"grades: {total} new")
            return ProcessResult("sent", api_calls=api_calls, api_errors=api_errors)

        logger.warning("Уведомления: не удалось отправить оценки user_id=%d", user_id)
        return ProcessResult(
            "failed",
            retryable=True,
            api_calls=api_calls,
            api_errors=api_errors,
            error="send_failed",
        )

    if api_calls > 0 and api_errors == api_calls:
        return ProcessResult(
            "failed",
            retryable=True,
            api_calls=api_calls,
            api_errors=api_errors,
            error="mesh_api_unavailable",
        )

    return ProcessResult("no_changes", api_calls=api_calls, api_errors=api_errors)


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

    total_users = len(by_user)
    sent_count = 0
    skipped_count = 0
    error_count = 0
    api_calls_total = 0
    api_errors_total = 0

    for user_id, subs in by_user.items():
        try:
            result = await _process_homework_for_user(user_id, subs)
            api_calls_total += result.api_calls
            api_errors_total += result.api_errors

            if result.status == "sent":
                sent_count += 1
            elif result.status == "failed":
                error_count += 1
                if result.retryable:
                    _enqueue_retry(user_id, "homework", result.error)
            else:
                skipped_count += 1
        except Exception as e:
            logger.error("Уведомления: ошибка ДЗ для user_id=%d: %s", user_id, e)
            error_count += 1
            _enqueue_retry(user_id, "homework", str(e))

    logger.info(
        "Уведомления: ДЗ — отправлено %d из %d, без изменений: %d, ошибок: %d",
        sent_count,
        total_users,
        skipped_count,
        error_count,
    )
    await _handle_outage_state("homework", api_calls_total, api_errors_total)
    await save_notification_run("homework", date.today())


def _parse_time_hhmm(value: Optional[str]) -> Optional[dt_time]:
    """Парсит HH:MM в time, иначе None."""
    if not value:
        return None
    try:
        hh, mm = value.strip().split(":")
        return dt_time(hour=int(hh), minute=int(mm))
    except Exception:
        return None


def _is_after_lesson_window(now_local: datetime, lesson_end: dt_time, delay_minutes: int) -> bool:
    """Проверяет, прошло ли delay_minutes после времени окончания урока."""
    send_after = now_local.replace(
        hour=lesson_end.hour,
        minute=lesson_end.minute,
        second=0,
        microsecond=0,
    ) + timedelta(minutes=delay_minutes)
    return now_local >= send_after


async def _is_student_homework_window_open(
    *,
    student_id: int,
    token: str,
    profile_id: int,
    now_local: datetime,
) -> tuple[bool, int, int]:
    """
    Для student: отправляем ДЗ только после последнего урока + 30 минут.
    Возвращает: (ok_to_send, api_calls, api_errors).
    """
    api_calls = 0
    api_errors = 0

    client = MeshClient()
    try:
        api_calls += 1
        lessons = await client.get_schedule(
            student_id=student_id,
            date_str=now_local.date().isoformat(),
            token=token,
            profile_id=profile_id,
        )
    except (AuthenticationError, MeshAPIError) as e:
        api_errors += 1
        logger.warning(
            "ДЗ window: ошибка расписания для student_id=%d: %s",
            student_id, e
        )
        return False, api_calls, api_errors
    finally:
        await client.close()

    lesson_ends: list[dt_time] = []
    for lesson in lessons or []:
        parsed = _parse_time_hhmm(getattr(lesson, "time_end", None))
        if parsed:
            lesson_ends.append(parsed)

    if lesson_ends:
        last_end = max(lesson_ends)
        return _is_after_lesson_window(now_local, last_end, _HOMEWORK_SEND_DELAY_MIN), api_calls, api_errors

    # Если уроков нет, используем стандартный порог времени из настроек.
    fallback_time = _parse_time_hhmm(getattr(settings, "HOMEWORK_NOTIFICATION_TIME", "19:00")) or dt_time(19, 0)
    return now_local.time() >= fallback_time, api_calls, api_errors


async def _process_homework_for_user(user_id: int, subs: list) -> ProcessResult:
    """Обработать уведомления о ДЗ для одного пользователя."""
    api_calls = 0
    api_errors = 0

    try:
        token = await ensure_token(user_id)
    except Exception as e:
        logger.warning("Уведомления ДЗ: не удалось получить токен для user_id=%d: %s", user_id, e)
        return ProcessResult("failed", retryable=True, error=f"token_error: {e}")

    if not token:
        logger.warning("Уведомления ДЗ: пустой токен для user_id=%d", user_id)
        return ProcessResult("failed", retryable=False, error="empty_token")

    user = await get_user(user_id)
    profile_id = user.get("mesh_profile_id") if user else None
    if not profile_id:
        logger.warning("Уведомления ДЗ: отсутствует profile_id для user_id=%d", user_id)
        return ProcessResult("failed", retryable=False, error="missing_profile_id")

    children = await get_user_children(user_id)
    if not children:
        logger.warning("Уведомления ДЗ: не найдены дети для user_id=%d", user_id)
        return ProcessResult("failed", retryable=False, error="missing_children")

    tz = pytz.timezone(settings.TIMEZONE)
    now_local = datetime.now(tz)
    today = now_local.date()
    tomorrow = _next_school_day(today)
    tomorrow_str = tomorrow.isoformat()
    homework_summaries = []
    ready_children = 0

    for child in children:
        allow_send, window_calls, window_errors = await _is_student_homework_window_open(
            student_id=child["student_id"],
            token=token,
            profile_id=profile_id,
            now_local=now_local,
        )
        api_calls += window_calls
        api_errors += window_errors
        if not allow_send:
            continue

        if await was_homework_summary_sent(user_id, child["child_id"], tomorrow_str):
            continue

        ready_children += 1

        client = MeshClient()
        try:
            api_calls += 1
            homework_list = await client.get_homework(
                student_id=child["student_id"],
                from_date=tomorrow_str,
                to_date=tomorrow_str,
                token=token,
                profile_id=profile_id,
            )
        except (AuthenticationError, MeshAPIError) as e:
            api_errors += 1
            logger.warning("Уведомления ДЗ: ошибка МЭШ API для child %d: %s", child["student_id"], e)
            continue
        finally:
            await client.close()

        hw_dicts = [
            {
                "subject": hw.subject,
                "assignment": hw.assignment,
                "due_date": hw.due_date,
            }
            for hw in homework_list
        ]

        if hw_dicts:
            await cache_new_homework(child["child_id"], hw_dicts)

        child_name = f"{child['first_name']} {child['last_name']}"
        homework_summaries.append((child, child_name, hw_dicts))


    if homework_summaries:
        text = _format_homework_notification(
            [(child_name, hw_list) for _, child_name, hw_list in homework_summaries],
            tomorrow,
        )
        sent_ok = await _safe_send_message(user_id, text)

        if sent_ok:
            for child, _, _ in homework_summaries:
                cached_hw = await get_unnotified_homework_for_date(child["child_id"], tomorrow_str)
                ids = [hw["homework_id"] for hw in cached_hw]
                await mark_homework_notified(ids)
                await mark_homework_summary_sent(user_id, child["child_id"], tomorrow_str)

            total = sum(len(h) for _, _, h in homework_summaries)
            await log_activity(
                user_id,
                "notification_sent",
                f"homework_summary: children={len(homework_summaries)}, items={total}, due_date={tomorrow_str}",
            )
            return ProcessResult("sent", api_calls=api_calls, api_errors=api_errors)

        logger.warning("Уведомления ДЗ: не удалось отправить user_id=%d", user_id)
        return ProcessResult(
            "failed",
            retryable=True,
            api_calls=api_calls,
            api_errors=api_errors,
            error="send_failed",
        )

    if api_calls > 0 and api_errors == api_calls:
        return ProcessResult(
            "failed",
            retryable=True,
            api_calls=api_calls,
            api_errors=api_errors,
            error="mesh_api_unavailable",
        )

    if ready_children > 0:
        return ProcessResult("no_changes", api_calls=api_calls, api_errors=api_errors)

    return ProcessResult("no_changes", api_calls=api_calls, api_errors=api_errors)


# ============================================================================
# ПЛАНИРОВЩИК НАПОМИНАНИЙ (v1.2.0)
# ============================================================================

def _is_control_lesson(lesson_type: Optional[str], subject: Optional[str]) -> bool:
    """Определяет, относится ли урок к контрольным/проверочным."""
    source = f"{lesson_type or ''} {subject or ''}".lower()
    return any(keyword in source for keyword in _CONTROL_LESSON_KEYWORDS)


def _format_planner_notification(
    controls_by_child: list[tuple[str, list[str]]],
    homework_by_child: list[tuple[str, list[tuple[str, str]]]],
    due_date: date,
) -> str:
    """Форматирует вечернее напоминание: контрольные и ДЗ на завтра."""
    lines = [
        f"<b>Напоминание на завтра ({due_date.strftime('%d.%m.%Y')})</b>",
        "",
    ]

    if controls_by_child:
        lines.append("<b>Контрольные и проверочные:</b>")
        for child_name, subjects in controls_by_child:
            if len(controls_by_child) > 1:
                lines.append(f"• <b>{html.escape(child_name)}</b>")
            for subject in subjects:
                lines.append(f"  - {html.escape(subject)}")
        lines.append("")

    if homework_by_child:
        lines.append("<b>Домашние задания со сроком на завтра:</b>")
        for child_name, hw_items in homework_by_child:
            if len(homework_by_child) > 1:
                lines.append(f"• <b>{html.escape(child_name)}</b>")
            for subject, assignment in hw_items:
                safe_subject = html.escape(subject)
                safe_assignment = html.escape(assignment or "—")
                if len(safe_assignment) > 160:
                    safe_assignment = safe_assignment[:157] + "..."
                lines.append(f"  - {safe_subject}: {safe_assignment}")
        lines.append("")

    lines.append("Удачи! ✨")
    return "\n".join(lines).strip()


async def _send_planner_reminders() -> None:
    """Ежедневные вечерние напоминания о контрольных и ДЗ на завтра."""
    logger.info("Planner reminders: запуск ежедневных напоминаний...")

    subscribers = await get_users_with_notifications("homework")
    if not subscribers:
        logger.info("Planner reminders: нет подписчиков (homework disabled)")
        return

    by_user = defaultdict(list)
    for sub in subscribers:
        by_user[sub["user_id"]].append(sub)

    total_users = len(by_user)
    sent_count = 0
    skipped_count = 0
    error_count = 0

    tomorrow = _next_school_day(date.today())

    for user_id in by_user:
        try:
            token = await ensure_token(user_id)
            if not token:
                skipped_count += 1
                continue

            user = await get_user(user_id)
            profile_id = user.get("mesh_profile_id") if user else None
            mes_role = user.get("mesh_role", "parent") if user else "parent"
            if not profile_id:
                skipped_count += 1
                continue

            children = await get_user_children(user_id)
            if not children:
                skipped_count += 1
                continue

            controls_by_child: list[tuple[str, list[str]]] = []
            homework_by_child: list[tuple[str, list[tuple[str, str]]]] = []

            for child in children:
                child_name = f"{child['first_name']} {child['last_name']}"
                client = MeshClient()
                try:
                    lessons = await client.get_schedule(
                        student_id=child["student_id"],
                        date_str=tomorrow.isoformat(),
                        token=token,
                        person_id=child.get("person_id"),
                        mes_role=mes_role,
                    )
                    controls = [
                        lesson.subject
                        for lesson in lessons
                        if _is_control_lesson(lesson.lesson_type, lesson.subject)
                    ]
                    if controls:
                        controls_by_child.append((child_name, controls))

                    homework = await client.get_homework(
                        student_id=child["student_id"],
                        from_date=tomorrow.isoformat(),
                        to_date=tomorrow.isoformat(),
                        token=token,
                        profile_id=profile_id,
                    )
                    hw_items = [(hw.subject, hw.assignment) for hw in homework]
                    if hw_items:
                        homework_by_child.append((child_name, hw_items))

                except (AuthenticationError, MeshAPIError) as e:
                    logger.warning("Planner reminders: user_id=%d child_id=%d error=%s", user_id, child["child_id"], e)
                finally:
                    await client.close()

            if not controls_by_child and not homework_by_child:
                skipped_count += 1
                continue

            text = _format_planner_notification(controls_by_child, homework_by_child, tomorrow)
            sent_ok = await _safe_send_message(user_id, text)
            if sent_ok:
                sent_count += 1
                controls_total = sum(len(x[1]) for x in controls_by_child)
                homework_total = sum(len(x[1]) for x in homework_by_child)
                await log_activity(
                    user_id,
                    "notification_sent",
                    f"planner: controls={controls_total}, homework={homework_total}",
                )
            else:
                error_count += 1
        except Exception as e:
            logger.error("Planner reminders: user_id=%d failed: %s", user_id, e)
            error_count += 1

    logger.info(
        "Planner reminders: отправлено %d из %d, пропущено: %d, ошибок: %d",
        sent_count, total_users, skipped_count, error_count
    )
    await save_notification_run("planner", date.today())


async def _process_custom_reminders() -> None:
    """Обрабатывает пользовательские ежедневные напоминания /remind."""
    tz = pytz.timezone(settings.TIMEZONE)
    now = datetime.now(tz)
    now_hhmm = now.strftime("%H:%M")
    today = now.date()

    due_items = await get_due_custom_reminders(now_hhmm, today)
    if not due_items:
        return

    logger.info("Custom reminders: due at %s, count=%d", now_hhmm, len(due_items))

    for item in due_items:
        reminder_id = item["reminder_id"]
        user_id = item["user_id"]
        reminder_text = item["reminder_text"]

        text = (
            "<b>Напоминание</b>\n"
            f"{html.escape(reminder_text)}"
        )
        sent_ok = await _safe_send_message(user_id, text)
        if sent_ok:
            await mark_custom_reminder_sent(reminder_id, today)
        else:
            logger.warning(
                "Custom reminders: send failed reminder_id=%d user_id=%d",
                reminder_id, user_id
            )


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
            due_date = hw.get("due_date")
            if hasattr(due_date, "strftime"):
                due_label = due_date.strftime("%d.%m.%Y")
            else:
                due_label = html.escape(str(due_date or "—"))
            if len(assignment) > 200:
                assignment = assignment[:197] + "..."
            lines.append(f"  [{due_label}] {subject}: {assignment}")

    return "\n".join(lines)


# ============================================================================
# ОТПРАВКА
# ============================================================================

def _format_notification_date(value: Optional[Union[date, str]] = None) -> str:
    """Return DD.MM.YYYY for notification headers."""
    if value is None:
        value = date.today()
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).strftime("%d.%m.%Y")
        except ValueError:
            pass
    return html.escape(str(value))


def _format_grades_notification(all_new_grades: list, report_date: Optional[Union[date, str]] = None) -> str:
    """Format grades notification with explicit child name and date."""
    lines = [f"<b>Новые оценки за сегодня, {_format_notification_date(report_date)}</b>\n"]

    for child_name, grades in all_new_grades:
        lines.append(f"\n<b>{html.escape(child_name)}</b>")

        for g in grades:
            subject = html.escape(g["subject"])
            value = html.escape(str(g["grade_value"]))
            line = f"  {subject} — <b>{value}</b>"
            if g.get("lesson_type"):
                line += f" ({html.escape(g['lesson_type'])})"
            lines.append(line)

    return "\n".join(lines)


def _format_homework_notification(all_new_hw: list, due_date: Optional[Union[date, str]] = None) -> str:
    """Format per-student homework summary for the next school day."""
    lines = [f"<b>Домашние задания на {_format_notification_date(due_date)}</b>\n"]

    for child_name, hw_list in all_new_hw:
        lines.append(f"\n<b>{html.escape(child_name)}</b>")

        if not hw_list:
            lines.append("  Домашних заданий нет.")
            continue

        for hw in hw_list:
            subject = html.escape(hw["subject"])
            assignment = html.escape(hw["assignment"] or "—")
            if len(assignment) > 200:
                assignment = assignment[:197] + "..."
            lines.append(f"  {subject}: {assignment}")

    return "\n".join(lines)


_SEND_RETRIES = 3
_SEND_RETRY_DELAY = 3  # секунд


async def _safe_send_message(user_id: int, text: str) -> bool:
    """Отправить сообщение с обработкой ошибок Telegram. Возвращает True при успехе."""
    if not _bot:
        logger.error("Уведомления: bot не инициализирован")
        return False

    for attempt in range(_SEND_RETRIES):
        try:
            await _bot.send_message(user_id, text, parse_mode="HTML")
            return True
        except TelegramForbiddenError:
            logger.warning("Уведомления: бот заблокирован user_id=%d, отключаю уведомления", user_id)
            await disable_all_notifications(user_id)
            return False
        except TelegramBadRequest as e:
            logger.error("Уведомления: ошибка отправки user_id=%d: %s", user_id, e)
            return False
        except Exception as e:
            if attempt < _SEND_RETRIES - 1:
                logger.warning("Уведомления: retry %d/%d для user_id=%d: %s",
                               attempt + 1, _SEND_RETRIES, user_id, e)
                await asyncio.sleep(_SEND_RETRY_DELAY)
            else:
                logger.error("Уведомления: не удалось отправить user_id=%d после %d попыток: %s",
                             user_id, _SEND_RETRIES, e)
                return False
    return False


def _enqueue_retry(user_id: int, notif_type: str, error: Optional[str]) -> None:
    """Добавить пользователя в retry-очередь при временной ошибке."""
    key = (user_id, notif_type)
    item = _retry_queue.get(key)
    if item:
        return

    _retry_queue[key] = {
        "attempts": 0,
        "next_retry_at": datetime.now(pytz.utc) + timedelta(seconds=_RETRY_BASE_DELAY_SEC),
        "last_error": error or "temporary_error",
    }
    logger.warning(
        "Retry-queue: добавлен user_id=%d type=%s (error=%s)",
        user_id, notif_type, error or "n/a",
    )


async def _process_retry_queue() -> None:
    """Переобрабатывает пользователей с временными ошибками уведомлений."""
    if not _retry_queue:
        return

    now_utc = datetime.now(pytz.utc)
    logger.info("Retry-queue: запуск, элементов=%d", len(_retry_queue))

    for (user_id, notif_type), item in list(_retry_queue.items()):
        if item["next_retry_at"] > now_utc:
            continue

        subscribers = await get_users_with_notifications(notif_type)
        by_user = defaultdict(list)
        for sub in subscribers:
            by_user[sub["user_id"]].append(sub)

        subs = by_user.get(user_id)
        if not subs:
            logger.info("Retry-queue: удалён user_id=%d type=%s (подписка отключена)", user_id, notif_type)
            _retry_queue.pop((user_id, notif_type), None)
            continue

        process_func = _process_grades_for_user if notif_type == "grades" else _process_homework_for_user
        try:
            result = await process_func(user_id, subs)
        except Exception as e:
            result = ProcessResult("failed", retryable=True, error=str(e))

        if result.status in ("sent", "no_changes") or not result.retryable:
            logger.info(
                "Retry-queue: завершено user_id=%d type=%s status=%s",
                user_id, notif_type, result.status,
            )
            _retry_queue.pop((user_id, notif_type), None)
            continue

        item["attempts"] += 1
        if item["attempts"] >= _RETRY_MAX_ATTEMPTS:
            logger.error(
                "Retry-queue: исчерпаны попытки user_id=%d type=%s (last_error=%s)",
                user_id, notif_type, result.error or item.get("last_error"),
            )
            _retry_queue.pop((user_id, notif_type), None)
            continue

        delay = _RETRY_BASE_DELAY_SEC * (2 ** (item["attempts"] - 1))
        item["next_retry_at"] = now_utc + timedelta(seconds=delay)
        item["last_error"] = result.error or item["last_error"]
        logger.warning(
            "Retry-queue: повтор user_id=%d type=%s через %ds (attempt %d/%d)",
            user_id, notif_type, delay, item["attempts"], _RETRY_MAX_ATTEMPTS,
        )


async def _send_admin_alert(text: str) -> None:
    """Отправить уведомление админу о проблеме доступности API."""
    admin_id = getattr(settings, "ADMIN_ID", None)
    if not admin_id or not _bot:
        return
    try:
        await _bot.send_message(admin_id, text, parse_mode="HTML")
    except Exception as e:
        logger.warning("Admin alert: не удалось отправить ADMIN_ID=%s: %s", admin_id, e)


async def _handle_outage_state(notif_type: str, api_calls: int, api_errors: int) -> None:
    """Обновляет состояние недоступности МЭШ API и при необходимости шлёт алерт админу."""
    state = _outage_state[notif_type]
    now_utc = datetime.now(pytz.utc)

    is_outage = (
        api_calls >= _OUTAGE_MIN_API_CALLS
        and api_errors / max(api_calls, 1) >= _OUTAGE_RATIO_THRESHOLD
    )

    if not is_outage:
        if state["consecutive"] > 0:
            logger.info("Outage monitor: %s восстановлен (calls=%d errors=%d)", notif_type, api_calls, api_errors)
        state["consecutive"] = 0
        return

    state["consecutive"] += 1
    logger.warning(
        "Outage monitor: %s похоже недоступен (%d/%d ошибок), подряд запусков=%d",
        notif_type, api_errors, api_calls, state["consecutive"],
    )

    should_alert = state["consecutive"] >= _OUTAGE_RUNS_FOR_ALERT
    if should_alert and state["last_alert_at"] is not None:
        elapsed = (now_utc - state["last_alert_at"]).total_seconds()
        should_alert = elapsed >= _OUTAGE_ALERT_COOLDOWN_SEC

    if not should_alert:
        return

    state["last_alert_at"] = now_utc
    await _send_admin_alert(
        "<b>⚠️ МЭШ API нестабилен</b>\n"
        f"Тип уведомлений: <b>{html.escape(notif_type)}</b>\n"
        f"Ошибок API: <b>{api_errors}</b> из <b>{api_calls}</b>\n"
        f"Подряд проблемных запусков: <b>{state['consecutive']}</b>\n\n"
        "Включена retry-очередь. Проверьте доступность МЭШ и сетевую связность."
    )


# ============================================================================
# ПРОВЕРКА ПРОПУЩЕННЫХ УВЕДОМЛЕНИЙ
# ============================================================================

async def check_and_send_missed(bot: Bot):
    """Проверяет и досылает пропущенные уведомления (бот был выключен).

    Вызывается один раз при старте бота, после scheduler.start().
    Для каждого типа: если последний запуск < сегодня И текущее время > запланированного — отправить.
    """
    tz = pytz.timezone(settings.TIMEZONE)
    now = datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")

    checks = [
        ("grades", getattr(settings, "GRADES_NOTIFICATION_TIME", "18:00"), _send_grades_notifications),
        ("homework", getattr(settings, "HOMEWORK_NOTIFICATION_TIME", "19:00"), _send_homework_notifications),
        ("planner", getattr(settings, "REMINDER_NOTIFICATION_TIME", "20:00"), _send_planner_reminders),
    ]

    for notif_type, scheduled_time, send_func in checks:
        if not isinstance(scheduled_time, str) or ":" not in scheduled_time:
            logger.warning("Пропущенные: %s — некорректное время '%s', пропуск", notif_type, scheduled_time)
            continue
        scheduled_h, scheduled_m = scheduled_time.split(":")
        scheduled_dt = now.replace(
            hour=int(scheduled_h), minute=int(scheduled_m), second=0, microsecond=0
        )

        if now < scheduled_dt:
            logger.info("Пропущенные: %s — ещё не %s, пропуск", notif_type, scheduled_time)
            continue

        last_run = await get_last_notification_run(notif_type)

        if last_run and last_run >= today_str:
            logger.info("Пропущенные: %s — уже отправлены сегодня (%s), пропуск", notif_type, last_run)
            continue

        logger.warning("Пропущенные: %s — последний запуск=%s, отправляем сейчас...", notif_type, last_run)
        try:
            await send_func()
        except Exception as e:
            logger.error("Пропущенные: %s — ошибка: %s", notif_type, e)


# ============================================================================
# ОЧИСТКА КЕША
# ============================================================================

async def _cleanup_stale_cache_on_start():
    """Помечает записи кеша старше 2 дней как отправленные (уже неактуальны)."""
    from core.database import get_db
    try:
        db = get_db()
        conn = await db.connect()
        for table in ("grades_cache", "homework_cache"):
            await conn.execute(
                f"UPDATE {table} SET is_notified = 1 "
                f"WHERE is_notified = 0 AND created_at < datetime('now', '-2 days')"
            )
        await conn.commit()
        logger.info("Уведомления: устаревший кеш (>2 дней) помечен при старте")
    except Exception as e:
        logger.warning("Уведомления: не удалось очистить кеш при старте: %s", e)


async def _cleanup_cache_job():
    """Еженедельная очистка старого кеша."""
    logger.info("Уведомления: очистка кеша старше 30 дней...")
    await cleanup_old_cache(30)
    logger.info("Уведомления: очистка кеша завершена")
