"""Tests for v1.7.0 reports helpers."""

from datetime import date

from handlers.reports import _period_dates, _safe_period_label
from services.report_documents import _chunk_line, _normalize_lines


def test_safe_period_label_defaults_to_today():
    assert _safe_period_label("today") == "today"
    assert _safe_period_label("week") == "week"
    assert _safe_period_label("unknown") == "today"


def test_period_dates_ranges():
    from_date, to_date = _period_dates("week")
    assert isinstance(from_date, date)
    assert isinstance(to_date, date)
    assert (to_date - from_date).days == 6

    from_month, to_month = _period_dates("month")
    assert (to_month - from_month).days == 29


def test_chunk_line_splits_long_text():
    text = "word " * 80
    chunks = _chunk_line(text, max_chars=50)
    assert len(chunks) > 1
    assert all(len(c) <= 50 for c in chunks)


def test_normalize_lines_keeps_empty_rows():
    lines = _normalize_lines(["a", "", "b"])
    assert "a" in lines
    assert "b" in lines
    assert "" in lines
