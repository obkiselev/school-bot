"""Tests for admin web helpers (v1.6.0)."""

from database.crud import normalize_broadcast_roles
from services.admin_web import _sanitize_broadcast_text


def test_normalize_broadcast_roles_filters_and_deduplicates():
    roles = normalize_broadcast_roles(["student", "parent", "student", "invalid", "ADMIN"])
    assert roles == ["student", "parent", "admin"]


def test_normalize_broadcast_roles_defaults():
    assert normalize_broadcast_roles([]) == ["student", "parent"]
    assert normalize_broadcast_roles(None) == ["student", "parent"]


def test_sanitize_broadcast_text_trims_and_limits():
    raw = "  hello  "
    assert _sanitize_broadcast_text(raw) == "hello"

    long_text = "x" * 5000
    assert len(_sanitize_broadcast_text(long_text)) == 4000
