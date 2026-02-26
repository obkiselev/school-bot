import re


def check_answer(question: dict, user_answer: str) -> bool:
    """Check if the user's answer is correct for the given question."""
    q_type = question["type"]
    correct = question["correct"]

    if q_type == "multiple_choice":
        return _normalize(user_answer) == _normalize(correct)

    elif q_type == "true_false":
        return _normalize(user_answer) == _normalize(correct)

    elif q_type == "fill_blank":
        return _normalize(user_answer) == _normalize(correct)

    elif q_type == "translation":
        if _normalize(user_answer) == _normalize(correct):
            return True
        # Check alternative accepted answers
        for alt in question.get("accept_also", []):
            if _normalize(user_answer) == _normalize(alt):
                return True
        return False

    return False


def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, strip, remove punctuation."""
    text = text.strip().lower()
    text = re.sub(r"[.,!?;:\"'()—–\-]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text
