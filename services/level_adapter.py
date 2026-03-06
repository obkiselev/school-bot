"""Adaptive difficulty: grade extraction and CEFR level mapping."""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Grade -> CEFR level mapping per language
GRADE_LEVEL_MAP = {
    "English": {(1, 4): "A1", (5, 6): "A2", (7, 8): "B1", (9, 11): "B2"},
    "Spanish": {(1, 6): "A1", (7, 8): "A1-A2", (9, 11): "A2"},
}

# Levels available for manual selection (parents/admins)
AVAILABLE_LEVELS = {
    "English": ["A1", "A2", "B1", "B2", "C1"],
    "Spanish": ["A1", "A1-A2", "A2", "B1"],
}

DEFAULT_LEVEL = "A2"


def extract_grade(class_name: Optional[str]) -> Optional[int]:
    """Parse class_name to grade number: '5A' -> 5, '11Б' -> 11."""
    if not class_name:
        return None
    match = re.search(r"(\d+)", class_name)
    if match:
        return int(match.group(1))
    return None


def grade_to_language_level(grade: int, language: str) -> str:
    """Convert grade + language to CEFR level string."""
    lang_map = GRADE_LEVEL_MAP.get(language, {})
    for (low, high), level in lang_map.items():
        if low <= grade <= high:
            return level
    return DEFAULT_LEVEL


async def get_user_level(user_id: int, language: str) -> Optional[str]:
    """Auto-detect level for students, return None for parents/admins.

    Students: extract grade from first child's class_name -> CEFR level.
    Parents/admins: return None (they choose manually).
    """
    from database.crud import get_user_role, get_user_children

    role = await get_user_role(user_id)
    if role != "student":
        return None

    children = await get_user_children(user_id)
    if not children:
        return DEFAULT_LEVEL

    class_name = children[0].get("class_name")
    grade = extract_grade(class_name)
    if grade is None:
        return DEFAULT_LEVEL

    return grade_to_language_level(grade, language)
