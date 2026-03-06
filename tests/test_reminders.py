"""Тесты для функционала напоминаний v1.2.0."""

from datetime import date

from handlers.reminders import _is_valid_time, _format_list
from services.notification_service import _is_control_lesson, _format_planner_notification


def test_is_valid_time_accepts_correct_values():
    assert _is_valid_time("00:00")
    assert _is_valid_time("8:15")
    assert _is_valid_time("23:59")


def test_is_valid_time_rejects_invalid_values():
    assert not _is_valid_time("24:00")
    assert not _is_valid_time("12:60")
    assert not _is_valid_time("abc")


def test_is_control_lesson_by_lesson_type():
    assert _is_control_lesson("Контрольная работа", "Математика")
    assert _is_control_lesson("Проверочная", "Русский язык")


def test_is_control_lesson_by_subject_and_negative_case():
    assert _is_control_lesson(None, "Тест по биологии")
    assert not _is_control_lesson("Обычный урок", "Литература")


def test_format_planner_notification_contains_sections():
    text = _format_planner_notification(
        controls_by_child=[("Иван Иванов", ["Математика"])],
        homework_by_child=[("Иван Иванов", [("Русский язык", "упр. 25")])],
        due_date=date(2026, 3, 7),
    )
    assert "Напоминание на завтра" in text
    assert "Контрольные и проверочные" in text
    assert "Домашние задания со сроком на завтра" in text
    assert "Математика" in text
    assert "Русский язык" in text


def test_format_list_empty_and_non_empty():
    empty_text = _format_list([])
    assert "Пока нет ни одного напоминания" in empty_text

    filled_text = _format_list([
        {"reminder_id": 1, "reminder_time": "20:30", "reminder_text": "Проверить дневник"}
    ])
    assert "1." in filled_text
    assert "20:30" in filled_text
    assert "Проверить дневник" in filled_text
