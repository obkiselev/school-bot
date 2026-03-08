"""Reports and PDF export handler (v1.7.0)."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.crud import get_user, get_user_children, get_user_role, invalidate_token
from keyboards.main_menu import home_button
from mesh_api.client import MeshClient
from mesh_api.exceptions import AuthenticationError, MeshAPIError
from mesh_api.models import Grade, Lesson
from services.report_documents import build_report_pdf_bytes
from utils.token_manager import ensure_token

logger = logging.getLogger(__name__)

router = Router()


def _home_only_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[home_button()]])


def _period_week_dates(today: date) -> List[date]:
    monday = today - timedelta(days=today.weekday())
    return [monday + timedelta(days=i) for i in range(5)]


def _report_kind_buttons(student_id: int, include_grades: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="PDF: Расписание сегодня",
                callback_data=f"rpt:mk:{student_id}:schedule:today",
            )
        ],
        [
            InlineKeyboardButton(
                text="PDF: Расписание завтра",
                callback_data=f"rpt:mk:{student_id}:schedule:tomorrow",
            )
        ],
        [
            InlineKeyboardButton(
                text="PDF: Расписание неделя",
                callback_data=f"rpt:mk:{student_id}:schedule:week",
            )
        ],
    ]
    if include_grades:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text="PDF: Оценки сегодня",
                        callback_data=f"rpt:mk:{student_id}:grades:today",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="PDF: Оценки неделя",
                        callback_data=f"rpt:mk:{student_id}:grades:week",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="PDF: Оценки месяц",
                        callback_data=f"rpt:mk:{student_id}:grades:month",
                    )
                ],
            ]
        )
    rows.append([home_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _children_keyboard(children: List[Dict], include_grades: bool) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for child in children:
        title = f"{child.get('last_name', '')} {child.get('first_name', '')}".strip()
        if child.get("class_name"):
            title = f"{title} ({child['class_name']})"
        rows.append(
            [
                InlineKeyboardButton(
                    text=title or str(child["student_id"]),
                    callback_data=f"rpt:child:{child['student_id']}:{1 if include_grades else 0}",
                )
            ]
        )
    rows.append([home_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _period_dates(period: str) -> Tuple[date, date]:
    today = date.today()
    if period == "week":
        return today - timedelta(days=6), today
    if period == "month":
        return today - timedelta(days=29), today
    return today, today


async def _fetch_schedule(
    student_id: int,
    period: str,
    token: str,
    person_id: Optional[str],
    mes_role: str,
) -> List[Tuple[date, List[Lesson]]]:
    today = date.today()
    if period == "today":
        targets = [today]
    elif period == "tomorrow":
        targets = [today + timedelta(days=1)]
    else:
        targets = _period_week_dates(today)

    items: List[Tuple[date, List[Lesson]]] = []
    client = MeshClient()
    try:
        for day in targets:
            lessons = await client.get_schedule(
                student_id,
                day.isoformat(),
                token,
                person_id=person_id,
                mes_role=mes_role,
            )
            items.append((day, lessons))
    finally:
        await client.close()
    return items


async def _fetch_grades(
    student_id: int,
    period: str,
    token: str,
    profile_id: int,
) -> List[Grade]:
    from_date, to_date = _period_dates(period)
    client = MeshClient()
    try:
        return await client.get_grades(
            student_id=student_id,
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
            token=token,
            profile_id=profile_id,
        )
    finally:
        await client.close()


def _schedule_lines(items: List[Tuple[date, List[Lesson]]]) -> List[str]:
    lines: List[str] = []
    for day, lessons in items:
        lines.append(f"{day.isoformat()}:")
        if not lessons:
            lines.append("  no lessons")
            lines.append("")
            continue
        for lesson in lessons:
            subject = (lesson.subject or "-").strip()
            room = f", room {lesson.room}" if lesson.room else ""
            teacher = f", teacher {lesson.teacher}" if lesson.teacher else ""
            lines.append(
                f"  {lesson.number}. {lesson.time_start}-{lesson.time_end} {subject}{room}{teacher}"
            )
        lines.append("")
    return lines


def _grades_lines(grades: List[Grade]) -> List[str]:
    lines: List[str] = []
    if not grades:
        return ["No grades for selected period."]
    for grade in sorted(grades, key=lambda g: g.date, reverse=True):
        lesson_type = f" ({grade.lesson_type})" if grade.lesson_type else ""
        comment = f" | {grade.comment}" if grade.comment else ""
        lines.append(
            f"{grade.date.isoformat()} | {grade.subject} | {grade.grade_value}{lesson_type}{comment}"
        )
    return lines


def _safe_period_label(period: str) -> str:
    mapping = {"today": "today", "tomorrow": "tomorrow", "week": "week", "month": "month"}
    return mapping.get(period, "today")


@router.message(Command("report"))
async def cmd_report(message: Message) -> None:
    user_id = message.from_user.id
    role = await get_user_role(user_id)
    if not role:
        await message.answer("Сначала получите доступ у администратора.", reply_markup=_home_only_keyboard())
        return

    user = await get_user(user_id)
    if not user:
        await message.answer("Вы еще не зарегистрированы.", reply_markup=_home_only_keyboard())
        return

    children = await get_user_children(user_id)
    if not children:
        await message.answer("У вас нет привязанных детей.", reply_markup=_home_only_keyboard())
        return

    include_grades = role in ("admin", "parent")
    if len(children) > 1:
        await message.answer(
            "Выберите ребенка для PDF-отчета:",
            reply_markup=_children_keyboard(children, include_grades),
        )
        return

    student_id = children[0]["student_id"]
    await message.answer(
        "Выберите документ:",
        reply_markup=_report_kind_buttons(student_id, include_grades),
    )


@router.callback_query(F.data.startswith("rpt:child:"))
async def cb_report_child(callback: CallbackQuery) -> None:
    await callback.answer()
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        return
    try:
        student_id = int(parts[2])
        include_grades = parts[3] == "1"
    except ValueError:
        return
    await callback.message.edit_text(
        "Выберите документ:",
        reply_markup=_report_kind_buttons(student_id, include_grades),
    )


@router.callback_query(F.data.startswith("rpt:mk:"))
async def cb_make_report(callback: CallbackQuery) -> None:
    await callback.answer("Готовлю PDF...", show_alert=False)

    parts = (callback.data or "").split(":")
    if len(parts) != 5:
        return
    try:
        student_id = int(parts[2])
    except ValueError:
        return
    doc_type = parts[3]
    period = parts[4]

    user_id = callback.from_user.id
    children = await get_user_children(user_id)
    child_map = {c["student_id"]: c for c in children}
    if student_id not in child_map:
        await callback.message.answer("Ребенок не найден в вашем профиле.")
        return

    user = await get_user(user_id)
    role = await get_user_role(user_id)
    if not user or not role:
        await callback.message.answer("Пользователь не найден.")
        return

    child = child_map[student_id]
    child_title = f"{child.get('last_name', '')} {child.get('first_name', '')}".strip() or str(student_id)

    try:
        token = await ensure_token(user_id)
    except AuthenticationError as exc:
        await callback.message.answer(f"Ошибка авторизации МЭШ: {exc}")
        return

    period_label = _safe_period_label(period)
    try:
        if doc_type == "schedule":
            mes_role = user.get("mesh_role", "parent")
            person_id = child.get("person_id")
            items = await _fetch_schedule(student_id, period, token, person_id, mes_role)
            lines = _schedule_lines(items)
            pdf_bytes = build_report_pdf_bytes(
                title=f"Schedule report: {child_title}",
                subtitle=f"Period: {period_label}",
                lines=lines,
            )
            filename = f"schedule_{student_id}_{period_label}.pdf"
        elif doc_type == "grades":
            if role not in ("admin", "parent"):
                await callback.message.answer("Экспорт оценок доступен только admin/parent.")
                return
            profile_id = user.get("mesh_profile_id")
            if not profile_id:
                await callback.message.answer("Нужна перерегистрация МЭШ для выгрузки оценок.")
                return
            grades = await _fetch_grades(student_id, period, token, int(profile_id))
            lines = _grades_lines(grades)
            pdf_bytes = build_report_pdf_bytes(
                title=f"Grades report: {child_title}",
                subtitle=f"Period: {period_label}",
                lines=lines,
            )
            filename = f"grades_{student_id}_{period_label}.pdf"
        else:
            return
    except AuthenticationError:
        try:
            await invalidate_token(user_id)
            token = await ensure_token(user_id)
        except AuthenticationError as exc:
            await callback.message.answer(f"Повторная авторизация МЭШ не удалась: {exc}")
            return
        await callback.message.answer("Токен МЭШ обновлен. Нажмите кнопку отчета еще раз.")
        return
    except MeshAPIError as exc:
        await callback.message.answer(f"Сервис МЭШ временно недоступен: {exc}")
        return
    except RuntimeError as exc:
        await callback.message.answer(str(exc))
        return
    except Exception as exc:
        logger.exception("Failed to generate report PDF")
        await callback.message.answer(f"Не удалось сформировать PDF: {exc}")
        return

    await callback.message.answer_document(
        BufferedInputFile(pdf_bytes, filename=filename),
        caption=f"Готово: {filename}",
    )
