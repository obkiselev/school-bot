import json
import logging
import re

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {
    "multiple_choice": {"question", "options", "correct", "explanation"},
    "fill_blank": {"question", "correct", "explanation"},
    "translation": {"question", "correct", "explanation"},
    "true_false": {"question", "correct", "explanation"},
}


def parse_questions(raw_text: str) -> list[dict] | None:
    """Parse LLM output into a list of question dicts. Returns None on failure."""
    if not raw_text:
        return None

    # Try direct JSON parse
    questions = _try_parse_json(raw_text)

    # Try extracting from markdown code block
    if questions is None:
        match = re.search(r"```(?:json)?\s*(\[.+?])\s*```", raw_text, re.DOTALL)
        if match:
            questions = _try_parse_json(match.group(1))

    # Try finding array in the text
    if questions is None:
        match = re.search(r"(\[\s*\{.+}\s*])", raw_text, re.DOTALL)
        if match:
            questions = _try_parse_json(match.group(1))

    if questions is None:
        logger.error("Failed to parse LLM response as JSON")
        return None

    # Validate each question
    valid = []
    for q in questions:
        if _validate_question(q):
            valid.append(q)
        else:
            logger.warning(f"Skipping invalid question: {q}")

    return valid if valid else None


def _try_parse_json(text: str) -> list[dict] | None:
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _validate_question(q: dict) -> bool:
    q_type = q.get("type")
    if q_type not in REQUIRED_FIELDS:
        return False
    required = REQUIRED_FIELDS[q_type]
    return all(q.get(field) for field in required)
