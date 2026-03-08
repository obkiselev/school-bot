"""Tests for v1.5.0 quiz expansion."""

from keyboards.quiz_kb import language_keyboard
from handlers.import_questions import _validate_question
from llm.parser import parse_questions
from services.answer_checker import check_answer
from services.fallback_test_generator import generate_fallback_test


def test_answer_checker_matching_with_accept_also():
    question = {
        "type": "matching",
        "question": "Сопоставь",
        "correct": "клетка:структурная единица",
        "accept_also": ["клетка - структурная единица"],
        "explanation": "ok",
    }
    assert check_answer(question, "клетка - структурная единица")


def test_answer_checker_audio():
    question = {
        "type": "audio",
        "question": "Ответь",
        "correct": "лёгкие",
        "accept_also": ["легкие"],
        "explanation": "ok",
    }
    assert check_answer(question, "легкие")


def test_parser_accepts_matching_and_audio():
    raw = """
    [
      {"type":"matching","question":"Сопоставь термин","correct":"митоз","explanation":"ok"},
      {"type":"audio","question":"Прослушай и ответь","audio_text":"подсказка","correct":"лёгкие","explanation":"ok"}
    ]
    """
    parsed = parse_questions(raw)
    assert parsed is not None
    assert len(parsed) == 2
    assert parsed[0]["type"] == "matching"
    assert parsed[1]["type"] == "audio"


def test_language_keyboard_has_new_options():
    kb = language_keyboard()
    callbacks = {
        button.callback_data
        for row in kb.inline_keyboard
        for button in row
        if button.callback_data
    }
    assert "lang:French" in callbacks
    assert "lang:German" in callbacks
    assert "lang:Mathematics" in callbacks
    assert "lang:History" in callbacks
    assert "lang:Biology" in callbacks


def test_fallback_supports_school_subject():
    quiz = generate_fallback_test("Mathematics", "Линейные уравнения", 3, level="School")
    assert len(quiz) == 3
    assert all("Fallback" in item["question"] for item in quiz)


def test_import_audio_question_requires_audio_source():
    q_without_audio = {
        "type": "audio",
        "question": "Прослушай",
        "correct": "ответ",
        "explanation": "ok",
    }
    q_with_audio = dict(q_without_audio)
    q_with_audio["audio_file_id"] = "AwACAgIAAxkBAAIB..."
    assert not _validate_question(q_without_audio)
    assert _validate_question(q_with_audio)
