"""Тесты для services/analytics.py — аналитика оценок."""
import pytest
from datetime import date, timedelta
from unittest.mock import patch

from mesh_api.models import Grade
from services.analytics import (
    parse_grade_value,
    compute_subject_averages,
    compute_overall_average,
    compute_trends,
    compute_grade_distribution,
    get_analytics_periods,
    get_period_label,
    format_analytics,
)


# ============================================================================
# Хелперы
# ============================================================================

def _make_grade(subject="Математика", value="5", day_offset=0, lesson_type=None):
    """Создаёт Grade с указанными параметрами."""
    return Grade(
        subject=subject,
        grade_value=value,
        date=date.today() - timedelta(days=day_offset),
        lesson_type=lesson_type,
    )


# ============================================================================
# TestParseGradeValue
# ============================================================================

class TestParseGradeValue:
    def test_five(self):
        assert parse_grade_value("5") == 5.0

    def test_four(self):
        assert parse_grade_value("4") == 4.0

    def test_three(self):
        assert parse_grade_value("3") == 3.0

    def test_two(self):
        assert parse_grade_value("2") == 2.0

    def test_one(self):
        assert parse_grade_value("1") == 1.0

    def test_zachet_returns_none(self):
        assert parse_grade_value("зачет") is None

    def test_nezachet_returns_none(self):
        assert parse_grade_value("незачет") is None

    def test_absent_returns_none(self):
        assert parse_grade_value("н") is None

    def test_empty_string_returns_none(self):
        assert parse_grade_value("") is None

    def test_zero_returns_none(self):
        assert parse_grade_value("0") is None

    def test_six_returns_none(self):
        assert parse_grade_value("6") is None


# ============================================================================
# TestComputeSubjectAverages
# ============================================================================

class TestComputeSubjectAverages:
    def test_single_subject_single_grade(self):
        grades = [_make_grade("Математика", "5")]
        result = compute_subject_averages(grades)
        assert result == {"Математика": 5.0}

    def test_single_subject_multiple_grades(self):
        grades = [
            _make_grade("Математика", "5"),
            _make_grade("Математика", "4"),
            _make_grade("Математика", "3"),
        ]
        result = compute_subject_averages(grades)
        assert result == {"Математика": 4.0}

    def test_multiple_subjects(self):
        grades = [
            _make_grade("Математика", "5"),
            _make_grade("Физика", "4"),
            _make_grade("Физика", "4"),
        ]
        result = compute_subject_averages(grades)
        assert result == {"Математика": 5.0, "Физика": 4.0}

    def test_all_non_numeric(self):
        grades = [
            _make_grade("Физкультура", "зачет"),
            _make_grade("Физкультура", "зачет"),
        ]
        result = compute_subject_averages(grades)
        assert result == {}

    def test_mixed_numeric_and_non_numeric(self):
        grades = [
            _make_grade("Математика", "5"),
            _make_grade("Математика", "зачет"),
            _make_grade("Математика", "4"),
        ]
        result = compute_subject_averages(grades)
        assert result == {"Математика": 4.5}

    def test_empty_list(self):
        result = compute_subject_averages([])
        assert result == {}


# ============================================================================
# TestComputeOverallAverage
# ============================================================================

class TestComputeOverallAverage:
    def test_normal(self):
        grades = [
            _make_grade("Математика", "5"),
            _make_grade("Физика", "3"),
        ]
        result = compute_overall_average(grades)
        assert result == 4.0

    def test_all_non_numeric(self):
        grades = [_make_grade("Физкультура", "зачет")]
        result = compute_overall_average(grades)
        assert result is None

    def test_empty_list(self):
        result = compute_overall_average([])
        assert result is None

    def test_single_grade(self):
        grades = [_make_grade("Математика", "4")]
        result = compute_overall_average(grades)
        assert result == 4.0


# ============================================================================
# TestComputeTrends
# ============================================================================

class TestComputeTrends:
    def test_improvement(self):
        current = {"Математика": 4.5}
        previous = {"Математика": 3.0}
        result = compute_trends(current, previous)
        assert result == {"Математика": "up"}

    def test_decline(self):
        current = {"Математика": 3.0}
        previous = {"Математика": 4.5}
        result = compute_trends(current, previous)
        assert result == {"Математика": "down"}

    def test_stable(self):
        current = {"Математика": 4.0}
        previous = {"Математика": 4.1}
        result = compute_trends(current, previous)
        assert result == {"Математика": "stable"}

    def test_new_subject(self):
        current = {"Биология": 4.0}
        previous = {}
        result = compute_trends(current, previous)
        assert result == {"Биология": "new"}

    def test_dropped_subject_not_shown(self):
        current = {}
        previous = {"Физика": 4.0}
        result = compute_trends(current, previous)
        assert result == {}

    def test_empty_inputs(self):
        result = compute_trends({}, {})
        assert result == {}

    def test_exactly_at_threshold_is_stable(self):
        current = {"Математика": 4.3}
        previous = {"Математика": 4.0}
        result = compute_trends(current, previous)
        assert result == {"Математика": "stable"}

    def test_just_above_threshold_is_up(self):
        current = {"Математика": 4.31}
        previous = {"Математика": 4.0}
        result = compute_trends(current, previous)
        assert result == {"Математика": "up"}


# ============================================================================
# TestComputeGradeDistribution
# ============================================================================

class TestComputeGradeDistribution:
    def test_normal(self):
        grades = [
            _make_grade(value="5"),
            _make_grade(value="5"),
            _make_grade(value="4"),
            _make_grade(value="3"),
        ]
        result = compute_grade_distribution(grades)
        assert result == {5: 2, 4: 1, 3: 1}

    def test_with_non_numeric(self):
        grades = [
            _make_grade(value="5"),
            _make_grade(value="зачет"),
        ]
        result = compute_grade_distribution(grades)
        assert result == {5: 1}

    def test_empty_list(self):
        result = compute_grade_distribution([])
        assert result == {}


# ============================================================================
# TestGetAnalyticsPeriods
# ============================================================================

class TestGetAnalyticsPeriods:
    @patch("services.analytics.date")
    def test_week(self, mock_date):
        mock_date.today.return_value = date(2026, 3, 5)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

        current, previous = get_analytics_periods("week")
        assert current == (date(2026, 2, 27), date(2026, 3, 5))
        assert previous == (date(2026, 2, 20), date(2026, 2, 26))

    @patch("services.analytics.date")
    def test_month(self, mock_date):
        mock_date.today.return_value = date(2026, 3, 5)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

        current, previous = get_analytics_periods("month")
        assert current == (date(2026, 2, 4), date(2026, 3, 5))
        assert previous == (date(2026, 1, 5), date(2026, 2, 3))

    @patch("services.analytics.date")
    def test_quarter(self, mock_date):
        mock_date.today.return_value = date(2026, 3, 5)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

        current, previous = get_analytics_periods("quarter")
        assert current == (date(2025, 12, 6), date(2026, 3, 5))
        assert previous == (date(2025, 9, 7), date(2025, 12, 5))

    def test_default_is_week(self):
        current, previous = get_analytics_periods("unknown")
        today = date.today()
        assert current[1] == today
        assert (current[1] - current[0]).days == 6


# ============================================================================
# TestGetPeriodLabel
# ============================================================================

class TestGetPeriodLabel:
    def test_week(self):
        assert get_period_label("week") == "за неделю"

    def test_month(self):
        assert get_period_label("month") == "за месяц"

    def test_quarter(self):
        assert get_period_label("quarter") == "за четверть"

    def test_unknown(self):
        assert get_period_label("xxx") == "за неделю"


# ============================================================================
# TestFormatAnalytics
# ============================================================================

class TestFormatAnalytics:
    def test_no_grades(self):
        result = format_analytics([], [], "week")
        assert "числовых оценок нет" in result

    def test_with_grades_shows_average(self):
        current = [_make_grade("Математика", "5"), _make_grade("Математика", "4")]
        result = format_analytics(current, [], "week")
        assert "4.50" in result
        assert "Математика" in result

    def test_with_comparison(self):
        current = [_make_grade("Математика", "5")]
        previous = [_make_grade("Математика", "3")]
        result = format_analytics(current, previous, "week")
        assert "было" in result

    def test_distribution_shown(self):
        current = [
            _make_grade(value="5"),
            _make_grade(value="4"),
            _make_grade(value="3"),
        ]
        result = format_analytics(current, [], "week")
        assert "Распределение" in result
        assert "5" in result
        assert "4" in result
        assert "3" in result

    def test_best_worst_subjects(self):
        current = [
            _make_grade("Математика", "5"),
            _make_grade("Физика", "3"),
        ]
        result = format_analytics(current, [], "week")
        assert "Лучший" in result
        assert "Подтянуть" in result
        assert "Математика" in result
        assert "Физика" in result

    def test_html_escaping(self):
        current = [_make_grade("<script>alert(1)</script>", "5")]
        result = format_analytics(current, [], "week")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_only_non_numeric_grades(self):
        current = [_make_grade("Физкультура", "зачет")]
        result = format_analytics(current, [], "week")
        assert "числовых оценок нет" in result

    def test_single_subject_no_best_worst(self):
        """Когда один предмет — не показывать лучший/худший."""
        current = [_make_grade("Математика", "5")]
        result = format_analytics(current, [], "week")
        assert "Лучший" not in result
