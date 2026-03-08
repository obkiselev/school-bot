"""Quiz flow handlers — answering questions, cancel, results."""
import logging
import os
import time
import base64
from io import BytesIO
from datetime import date

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.types.input_file import BufferedInputFile, FSInputFile
from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)

from states.quiz_states import QuizFlow
from services.answer_checker import check_answer
from services.gamification import (
    calculate_xp, update_streak, check_badges, level_from_xp,
    format_results_text, get_theme, progress_bar,
)
from keyboards.quiz_kb import multiple_choice_keyboard, true_false_keyboard, cancel_keyboard
from keyboards.main_menu import quiz_home_keyboard

router = Router()


async def _send_audio_question(message: Message, header: str, question: dict):
    """Send audio-type question using Telegram voice/audio when available."""
    text = header + question["question"] + "\n\n🎧 Прослушай и напиши ответ:"
    await message.answer(text, reply_markup=cancel_keyboard())

    # Preferred source: Telegram file_id (best for production reliability)
    audio_file_id = question.get("audio_file_id")
    if audio_file_id:
        kind = (question.get("audio_kind") or "voice").lower()
        if kind == "audio":
            await message.answer_audio(audio=audio_file_id)
        else:
            await message.answer_voice(voice=audio_file_id)
        return

    # Optional source: HTTP URL
    audio_url = question.get("audio_url")
    if audio_url:
        kind = (question.get("audio_kind") or "audio").lower()
        if kind == "voice":
            await message.answer_voice(voice=audio_url)
        else:
            await message.answer_audio(audio=audio_url)
        return

    # Optional source: local file path
    audio_path = question.get("audio_path")
    if audio_path and os.path.exists(audio_path):
        kind = (question.get("audio_kind") or "audio").lower()
        input_file = FSInputFile(audio_path)
        if kind == "voice":
            await message.answer_voice(voice=input_file)
        else:
            await message.answer_audio(audio=input_file)
        return

    # Optional source: base64 payload
    audio_b64 = question.get("audio_base64")
    if audio_b64:
        try:
            data = base64.b64decode(audio_b64)
            file_name = question.get("audio_filename") or "question_audio.ogg"
            input_file = BufferedInputFile(data, filename=file_name)
            kind = (question.get("audio_kind") or "voice").lower()
            if kind == "audio":
                await message.answer_audio(audio=input_file)
            else:
                await message.answer_voice(voice=input_file)
            return
        except Exception:
            logger.warning("Invalid audio_base64 in question payload")

    # Last-resort fallback: transcript-style hint
    audio_text = question.get("audio_text")
    if audio_text:
        await message.answer(f"🔊 Аудио (текстовая версия): {audio_text}")
    else:
        await message.answer("⚠️ Для этого вопроса аудио не найдено. Напиши ответ по условию.")


async def _download_telegram_media_bytes(message: Message) -> tuple[bytes | None, str]:
    """Download voice/audio from Telegram and return bytes + suggested filename."""
    if message.voice:
        file_id = message.voice.file_id
        filename = f"voice_{message.voice.file_unique_id}.ogg"
        file_size = message.voice.file_size or 0
    elif message.audio:
        file_id = message.audio.file_id
        filename = message.audio.file_name or f"audio_{message.audio.file_unique_id}.mp3"
        file_size = message.audio.file_size or 0
    else:
        return None, "audio.bin"

    from config import settings
    max_bytes = settings.STT_MAX_FILE_MB * 1024 * 1024
    if file_size and file_size > max_bytes:
        await message.answer(f"⚠️ Файл слишком большой для распознавания (лимит {settings.STT_MAX_FILE_MB} МБ).")
        return None, filename

    tg_file = await message.bot.get_file(file_id)
    buf = BytesIO()
    await message.bot.download_file(tg_file.file_path, destination=buf)
    return buf.getvalue(), filename


async def start_quiz(message: Message, state: FSMContext):
    """Send the first question of the quiz."""
    await state.set_state(QuizFlow.answering_question)
    await state.update_data(question_sent_at=time.time(), answer_times=[])
    await _send_current_question(message, state)


async def _send_current_question(message: Message, state: FSMContext):
    """Send the current question based on its type."""
    data = await state.get_data()
    questions = data["questions"]
    index = data["current_index"]
    total = data["question_count"]

    if index >= len(questions):
        await _show_results(message, state)
        return

    q = questions[index]
    q_type = q["type"]

    # Progress bar header
    correct_so_far = data["correct_count"]
    pbar = progress_bar(index, total)
    header = f"\u2753 \u0412\u043e\u043f\u0440\u043e\u0441 {index + 1}/{total} {pbar}\n\u2705 {correct_so_far} \u043f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u044b\u0445\n\n"

    # Record when question was sent (for speed bonus)
    await state.update_data(question_sent_at=time.time())

    if q_type == "multiple_choice":
        text = header + q["question"]
        await message.answer(text, reply_markup=multiple_choice_keyboard(q["options"]))

    elif q_type == "true_false":
        text = header + q["question"]
        await message.answer(text, reply_markup=true_false_keyboard())

    elif q_type == "fill_blank":
        text = header + q["question"] + "\n\n\u270f\ufe0f \u041d\u0430\u043f\u0438\u0448\u0438 \u043e\u0442\u0432\u0435\u0442 (\u043f\u0440\u043e\u043f\u0443\u0449\u0435\u043d\u043d\u043e\u0435 \u0441\u043b\u043e\u0432\u043e):"
        await message.answer(text, reply_markup=cancel_keyboard())

    elif q_type == "translation":
        text = header + q["question"] + "\n\n\u270f\ufe0f \u041d\u0430\u043f\u0438\u0448\u0438 \u043f\u0435\u0440\u0435\u0432\u043e\u0434:"
        await message.answer(text, reply_markup=cancel_keyboard())

    elif q_type == "matching":
        text = (
            header
            + q["question"]
            + "\n\n✏️ Напиши соответствие в одну строку "
              "(например: термин:определение)."
        )
        await message.answer(text, reply_markup=cancel_keyboard())

    elif q_type == "audio":
        await _send_audio_question(message, header, q)

    else:
        await state.update_data(current_index=index + 1)
        await _send_current_question(message, state)


@router.callback_query(QuizFlow.answering_question, F.data.startswith("ans:"))
async def answer_via_button(callback: CallbackQuery, state: FSMContext):
    """Handle answers from inline keyboard buttons."""
    user_answer = callback.data.split(":", 1)[1]
    await callback.answer()
    await _process_answer(callback.message, state, user_answer)


@router.message(QuizFlow.answering_question, F.text)
async def answer_via_text(message: Message, state: FSMContext):
    """Handle answers typed as text."""
    user_answer = message.text.strip() if message.text else ""
    if not user_answer:
        await message.answer("\u041d\u0430\u043f\u0438\u0448\u0438 \u043e\u0442\u0432\u0435\u0442 \u0442\u0435\u043a\u0441\u0442\u043e\u043c:")
        return
    await _process_answer(message, state, user_answer)


@router.message(QuizFlow.answering_question, F.voice)
async def answer_via_voice(message: Message, state: FSMContext):
    """Handle voice answers using STT."""
    from llm.client import transcribe_audio_bytes, get_last_stt_error

    audio_bytes, filename = await _download_telegram_media_bytes(message)
    if not audio_bytes:
        return

    await message.answer("🎙 Распознаю голосовой ответ...")
    text = await transcribe_audio_bytes(audio_bytes, filename=filename)
    if not text:
        reason = get_last_stt_error() or "неизвестная ошибка STT"
        await message.answer(f"Не удалось распознать голосовое сообщение.\nПричина: {reason}\n\nПопробуй текстом.")
        return

    await message.answer(f"📝 Распознано: {text}")
    await _process_answer(message, state, text)


@router.message(QuizFlow.answering_question, F.audio)
async def answer_via_audio(message: Message, state: FSMContext):
    """Handle audio-file answers using STT."""
    from llm.client import transcribe_audio_bytes, get_last_stt_error

    audio_bytes, filename = await _download_telegram_media_bytes(message)
    if not audio_bytes:
        return

    await message.answer("🎧 Распознаю аудио-ответ...")
    text = await transcribe_audio_bytes(audio_bytes, filename=filename)
    if not text:
        reason = get_last_stt_error() or "неизвестная ошибка STT"
        await message.answer(f"Не удалось распознать аудио.\nПричина: {reason}\n\nПопробуй текстом.")
        return

    await message.answer(f"📝 Распознано: {text}")
    await _process_answer(message, state, text)


@router.callback_query(F.data == "cancel_quiz")
async def cancel_quiz(callback: CallbackQuery, state: FSMContext):
    """Cancel the current quiz and go home."""
    await state.clear()
    await callback.message.answer(
        "\u0422\u0435\u0441\u0442 \u043e\u0442\u043c\u0435\u043d\u0451\u043d. \u0412\u043e\u0437\u0432\u0440\u0430\u0449\u0430\u0435\u043c\u0441\u044f \u0432 \u043c\u0435\u043d\u044e.",
        reply_markup=quiz_home_keyboard(),
    )
    await callback.answer()


async def _process_answer(message: Message, state: FSMContext, user_answer: str):
    """Check the answer, show feedback, advance to next question."""
    data = await state.get_data()
    questions = data["questions"]
    index = data["current_index"]
    correct_count = data["correct_count"]
    answers = data["answers"]
    answer_times = data.get("answer_times", [])

    # Calculate answer time
    question_sent_at = data.get("question_sent_at", time.time())
    elapsed = time.time() - question_sent_at
    answer_times.append(elapsed)

    q = questions[index]
    is_correct = check_answer(q, user_answer)

    # Get user theme for feedback messages
    theme_key = data.get("theme_key", "neutral")
    theme = get_theme(theme_key)

    if is_correct:
        correct_count += 1
        feedback = theme["correct_msg"]
    else:
        correct_display = q["correct"]
        if len(correct_display) == 1 and correct_display.upper() in "ABCD" and q.get("options"):
            idx = ord(correct_display.upper()) - ord("A")
            if 0 <= idx < len(q["options"]):
                correct_display = q["options"][idx]
        feedback = f"{theme['wrong_msg']}\n\n\U0001f4dd \u041f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u044b\u0439 \u043e\u0442\u0432\u0435\u0442: {correct_display}"
        explanation = q.get("explanation", "")
        if explanation:
            feedback += f"\n\n\U0001f4a1 {explanation}"

    answers.append({
        "question_type": q["type"],
        "question_text": q["question"],
        "correct_answer": q["correct"],
        "user_answer": user_answer,
        "is_correct": is_correct,
        "explanation": q.get("explanation", ""),
    })

    await state.update_data(
        current_index=index + 1,
        correct_count=correct_count,
        answers=answers,
        answer_times=answer_times,
    )

    await message.answer(feedback)
    await _send_current_question(message, state)


async def _show_results(message: Message, state: FSMContext):
    """Show the final quiz results with gamification."""
    data = await state.get_data()
    language = data.get("language", "")
    topic = data.get("topic", "")
    total = data.get("question_count", 0)
    correct = data.get("correct_count", 0)
    answers = data.get("answers", [])
    answer_times = data.get("answer_times", [])
    user_id = data.get("user_id")

    actual_total = len(answers) or total
    percent = round(correct / actual_total * 100) if actual_total > 0 else 0

    # Save test session to DB
    difficulty = data.get("level")
    try:
        from database.crud import save_test_session
        if user_id:
            await save_test_session(user_id, language, topic, actual_total, correct, percent, answers, difficulty=difficulty)
    except Exception as e:
        logger.error("Failed to save test session for user_id=%s: %s", user_id, e)

    # Gamification
    theme_key = "neutral"
    xp_earned = 0
    streak_days = 0
    level = 1
    xp_total = 0
    new_badges = []

    if user_id:
        try:
            from database.crud import (
                ensure_user_stats, update_user_stats, get_user_badges,
                award_badge, get_distinct_languages, get_distinct_topics,
                get_stats_summary,
            )

            stats = await ensure_user_stats(user_id)
            theme_key = stats.get("theme") or "neutral"

            # Update streak
            streak_days, _ = update_streak(
                stats.get("last_quiz_date"), stats.get("current_streak", 0),
            )
            longest = max(streak_days, stats.get("longest_streak", 0))

            # Calculate XP
            xp_earned = calculate_xp(correct, actual_total, streak_days, answer_times)
            xp_total = (stats.get("xp_total") or 0) + xp_earned
            level = level_from_xp(xp_total)

            # XP today
            today_str = date.today().isoformat()
            if stats.get("xp_today_date") == today_str:
                xp_today = (stats.get("xp_today") or 0) + xp_earned
            else:
                xp_today = xp_earned

            # Save updated stats
            await update_user_stats(
                user_id, xp_total, xp_today, today_str,
                streak_days, longest, today_str, level,
            )

            # Check badges
            existing = set(await get_user_badges(user_id))
            summary = await get_stats_summary(user_id)
            langs = await get_distinct_languages(user_id)
            topics_count = await get_distinct_topics(user_id)
            all_fast = bool(answer_times) and all(t < 10.0 for t in answer_times)

            new_badges = check_badges(
                total_tests=summary.get("total_tests", 0),
                current_streak=streak_days,
                level=level,
                percent=percent,
                languages_used=langs,
                topics_used=topics_count,
                all_fast=all_fast,
                existing_badges=existing,
            )

            for badge_key in new_badges:
                await award_badge(user_id, badge_key)

        except Exception as e:
            logger.error("Gamification error for user_id=%s: %s", user_id, e)

    # Format themed result text
    text = format_results_text(
        theme_key=theme_key,
        language=language,
        topic=topic,
        correct=correct,
        total=actual_total,
        percent=percent,
        xp_earned=xp_earned,
        streak_days=streak_days,
        level=level,
        xp_total=xp_total,
        new_badges=new_badges,
    )

    await state.clear()
    await message.answer(text, reply_markup=quiz_home_keyboard())
