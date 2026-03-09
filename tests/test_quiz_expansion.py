"""Tests for v1.5.0 quiz expansion."""

from keyboards.quiz_kb import language_keyboard
from handlers.import_questions import _validate_question
from llm.parser import parse_questions
from services.answer_checker import check_answer
from services.fallback_test_generator import generate_fallback_test


def test_answer_checker_matching_with_accept_also():
    question = {
        "type": "matching",
        "question": "Sopostav",
        "correct": "kletka:strukturnaya edinitsa",
        "accept_also": ["kletka - strukturnaya edinitsa"],
        "explanation": "ok",
    }
    assert check_answer(question, "kletka - strukturnaya edinitsa")


def test_answer_checker_audio():
    question = {
        "type": "audio",
        "question": "Otvet",
        "correct": "legkie",
        "accept_also": ["lyogkie"],
        "explanation": "ok",
    }
    assert check_answer(question, "legkie")


def test_parser_accepts_matching_and_audio():
    raw = """
    [
      {"type":"matching","question":"Sopostav termin","correct":"mitoz","explanation":"ok"},
      {"type":"audio","question":"Proslushay i otvet","audio_text":"podskazka","correct":"legkie","explanation":"ok"}
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
    quiz = generate_fallback_test("Mathematics", "Linear equations", 3, level="School")
    assert len(quiz) == 3
    assert all("Fallback" in item["question"] for item in quiz)


def test_import_audio_question_requires_audio_source():
    q_without_audio = {
        "type": "audio",
        "question": "Proslushay",
        "correct": "otvet",
        "explanation": "ok",
    }
    q_with_audio = dict(q_without_audio)
    q_with_audio["audio_file_id"] = "AwACAgIAAxkBAAIB..."
    assert not _validate_question(q_without_audio)
    assert _validate_question(q_with_audio)


def test_fallback_english_no_repeats_for_10_questions():
    quiz = generate_fallback_test("English", "Present Simple", 10, level="A2")
    texts = [item["question"] for item in quiz]
    assert len(texts) == 10
    assert len(set(texts)) == 10


def test_fallback_subject_pools_are_not_mixed():
    history = generate_fallback_test("History", "Ancient world", 5, level="School")
    biology = generate_fallback_test("Biology", "Cell", 5, level="School")
    math = generate_fallback_test("Mathematics", "Fractions", 5, level="School")

    assert any("Patriotic War" in item["question"] for item in history)
    assert any("cell" in item["question"].lower() for item in biology)
    assert any("7 * 8" in item["question"] for item in math)
