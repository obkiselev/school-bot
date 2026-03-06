"""Data models for МЭШ API responses."""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, List


@dataclass
class Student:
    """Student profile from МЭШ."""
    student_id: int
    first_name: str
    last_name: str
    middle_name: Optional[str] = None
    class_name: Optional[str] = None
    school_name: Optional[str] = None
    person_id: Optional[str] = None        # contingent_guid — нужен для API событий
    class_unit_id: Optional[int] = None    # нужен для school_info


@dataclass
class Lesson:
    """Single lesson in schedule."""
    number: int
    subject: str
    time_start: str
    time_end: str
    teacher: Optional[str] = None
    room: Optional[str] = None
    lesson_type: Optional[str] = None


@dataclass
class Grade:
    """Student grade/mark."""
    subject: str
    grade_value: str
    date: date
    lesson_type: Optional[str] = None
    teacher: Optional[str] = None
    comment: Optional[str] = None


@dataclass
class Homework:
    """Homework assignment."""
    subject: str
    assignment: str
    due_date: date
    teacher: Optional[str] = None
    attachments: Optional[List[str]] = None


# ============================================================================
# КОНВЕРТЕРЫ: OctoDiary types → наши dataclasses
# ============================================================================

def student_from_octodiary(child) -> Student:
    """Конвертирует OctoDiary Child в наш Student."""
    return Student(
        student_id=child.id,
        first_name=child.first_name or "",
        last_name=child.last_name or "",
        middle_name=child.middle_name,
        class_name=child.class_name,
        school_name=child.school.short_name if child.school else None,
        person_id=child.contingent_guid,
        class_unit_id=child.class_unit_id,
    )


def lesson_from_event(event) -> Optional[Lesson]:
    """
    Конвертирует OctoDiary Event (Item) в наш Lesson.
    Пропускает события, которые не являются уроками.
    """
    if event.source != "PLAN":
        return None

    # Определяем номер урока (по порядку времени)
    time_start = ""
    time_end = ""
    if event.start_at:
        dt = event.start_at if isinstance(event.start_at, datetime) else event.start_at
        time_start = dt.strftime("%H:%M") if hasattr(dt, "strftime") else str(dt)
    if event.finish_at:
        dt = event.finish_at if isinstance(event.finish_at, datetime) else event.finish_at
        time_end = dt.strftime("%H:%M") if hasattr(dt, "strftime") else str(dt)

    return Lesson(
        number=0,  # Будет проставлен позже при сортировке
        subject=event.subject_name or event.title or "—",
        time_start=time_start,
        time_end=time_end,
        teacher=event.author_name,
        room=event.room_number or event.room_name,
        lesson_type=event.lesson_type,
    )


def grade_from_payload(payload) -> Optional[Grade]:
    """Конвертирует OctoDiary Marks.Payload в наш Grade."""
    if not payload.value:
        return None

    grade_date = date.today()
    if payload.date:
        dt = payload.date
        grade_date = dt.date() if isinstance(dt, datetime) else dt

    return Grade(
        subject=payload.subject_name or "—",
        grade_value=str(payload.value),
        date=grade_date,
        lesson_type=payload.control_form_name,
        comment=payload.comment,
    )


def homework_from_payload(payload) -> Optional[Homework]:
    """Конвертирует OctoDiary ShortHomeworks.Payload в наш Homework."""
    hw_date = date.today()
    if payload.date:
        dt = payload.date
        hw_date = dt.date() if isinstance(dt, datetime) else dt

    return Homework(
        subject=payload.subject_name or "—",
        assignment=payload.description or "—",
        due_date=hw_date,
    )
