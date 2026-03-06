"""Сервис уведомлений: проверка новых оценок/ДЗ, отправка через Telegram."""
import asyncio
import html
import logging
from dataclasses import dataclass
from collections import defaultdict
from datetime import date, timedelta
from datetime import datetime
from typing import Optional, Literal

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
    get_unnotified_homework,
    mark_homework_notified,
    disable_all_notifications,
    cleanup_old_cache,
    log_activity,
    save_notification_run,
    get_last_notification_run,
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
        misfire_grace_time=3600,
        coalesce=True,
    )

    # ДЗ — ежедневно
    scheduler.add_job(
        _send_homework_notifications,
        CronTrigger(hour=int(hw_h), minute=int(hw_m), timezone=tz),
        id="daily_homework",
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

    today = date.today()
    tomorrow = today + timedelta(days=1)
    all_new_hw = []

    for child in children:
        client = MeshClient()
        try:
            api_calls += 1
            homework_list = await client.get_homework(
                student_id=child["student_id"],
                from_date=tomorrow.isoformat(),
                to_date=(tomorrow + timedelta(days=6)).isoformat(),
                token=token,
                profile_id=profile_id,
            )
        except (AuthenticationError, MeshAPIError) as e:
            api_errors += 1
            logger.warning("Уведомления ДЗ: ошибка МЭШ API для child %d: %s", child["student_id"], e)
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


    if all_new_hw:
        text = _format_homework_notification(all_new_hw)
        sent_ok = await _safe_send_message(user_id, text)

        if sent_ok:
            for _, hw_list in all_new_hw:
                ids = [hw["homework_id"] for hw in hw_list]
                await mark_homework_notified(ids)

            total = sum(len(h) for _, h in all_new_hw)
            await log_activity(user_id, "notification_sent", f"homework: {total} new")
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

    return ProcessResult("no_changes", api_calls=api_calls, api_errors=api_errors)


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
        ("grades", settings.GRADES_NOTIFICATION_TIME, _send_grades_notifications),
        ("homework", settings.HOMEWORK_NOTIFICATION_TIME, _send_homework_notifications),
    ]

    for notif_type, scheduled_time, send_func in checks:
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
