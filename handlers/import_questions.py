"""Import quiz questions from JSON file (teacher/admin tool)."""
import json
from io import BytesIO

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from database.crud import get_user_role, save_imported_questions

router = Router()

ALLOWED_TYPES = {
    "multiple_choice",
    "fill_blank",
    "translation",
    "true_false",
    "matching",
    "audio",
}


def _validate_question(question: dict) -> bool:
    if not isinstance(question, dict):
        return False
    q_type = question.get("type")
    if q_type not in ALLOWED_TYPES:
        return False
    has_required = bool(question.get("question") and question.get("correct") and question.get("explanation"))
    if not has_required:
        return False

    if q_type == "audio":
        has_audio_source = any(
            question.get(key)
            for key in ("audio_file_id", "audio_url", "audio_path", "audio_base64")
        )
        return has_audio_source

    return True


@router.message(Command("import_questions"))
async def cmd_import_questions(message: Message):
    """Show import format and usage."""
    role = await get_user_role(message.from_user.id)
    if role not in {"admin", "parent"}:
        await message.answer("Команда доступна только администратору или родителю.")
        return

    await message.answer(
        "📥 Импорт вопросов из JSON\n\n"
        "Пришли JSON-файл с форматом:\n"
        "{\n"
        '  "language": "English | Spanish | French | German | Mathematics | History | Biology",\n'
        '  "level": "A1/A2/B1/B2/C1/School",\n'
        '  "topic": "Название темы",\n'
        '  "questions": [ ... ]\n'
        "}\n\n"
        "Каждый вопрос должен содержать минимум: type, question, correct, explanation.\n"
        "Поддерживаемые type: multiple_choice, fill_blank, translation, true_false, matching, audio."
        "\n\nДля type=audio желательно добавить источник:\n"
        "- audio_file_id (рекомендуется)\n"
        "- audio_url\n"
        "- audio_path\n"
        "- audio_base64 (+ audio_filename)"
    )


@router.message(F.document)
async def import_questions_document(message: Message):
    """Import questions from uploaded JSON file."""
    role = await get_user_role(message.from_user.id)
    if role not in {"admin", "parent"}:
        return

    doc = message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".json"):
        return

    file = await message.bot.get_file(doc.file_id)
    buffer = BytesIO()
    await message.bot.download_file(file.file_path, destination=buffer)

    try:
        payload = json.loads(buffer.getvalue().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        await message.answer("Не удалось прочитать JSON. Проверь формат файла.")
        return

    if not isinstance(payload, dict):
        await message.answer("JSON должен быть объектом с ключами language/level/topic/questions.")
        return

    language = str(payload.get("language") or "").strip()
    level = str(payload.get("level") or "").strip()
    topic = str(payload.get("topic") or "").strip()
    questions = payload.get("questions")

    if not language or not level or not topic or not isinstance(questions, list):
        await message.answer("В JSON обязательны: language, level, topic, questions (массив).")
        return

    valid_questions = [q for q in questions if _validate_question(q)]
    if not valid_questions:
        await message.answer("Нет валидных вопросов для импорта.")
        return

    inserted = await save_imported_questions(
        user_id=message.from_user.id,
        language=language,
        level=level,
        topic=topic,
        questions=valid_questions,
    )
    await message.answer(
        f"✅ Импорт завершён.\n"
        f"Язык/предмет: {language}\n"
        f"Уровень: {level}\n"
        f"Тема: {topic}\n"
        f"Загружено вопросов: {inserted}"
    )


@router.message(F.voice)
async def handle_voice_file_id(message: Message):
    """Return Telegram voice file_id for building audio questions."""
    role = await get_user_role(message.from_user.id)
    if role not in {"admin", "parent"}:
        return
    file_id = message.voice.file_id
    await message.answer(
        "🎤 Получен voice.\n"
        "Используй этот file_id в JSON вопросе:\n"
        f"`{file_id}`\n\n"
        "Пример полей: type=audio, audio_kind=voice, audio_file_id=<id>",
        parse_mode="Markdown",
    )


@router.message(F.audio)
async def handle_audio_file_id(message: Message):
    """Return Telegram audio file_id for building audio questions."""
    role = await get_user_role(message.from_user.id)
    if role not in {"admin", "parent"}:
        return
    file_id = message.audio.file_id
    await message.answer(
        "🎵 Получен audio.\n"
        "Используй этот file_id в JSON вопросе:\n"
        f"`{file_id}`\n\n"
        "Пример полей: type=audio, audio_kind=audio, audio_file_id=<id>",
        parse_mode="Markdown",
    )
