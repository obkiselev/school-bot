"""Quiz flow handlers — answering questions, cancel, results."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states.quiz_states import QuizFlow
from services.answer_checker import check_answer
from keyboards.quiz_kb import multiple_choice_keyboard, true_false_keyboard, cancel_keyboard
from keyboards.main_menu import quiz_home_keyboard

router = Router()


async def start_quiz(message: Message, state: FSMContext):
    """Send the first question of the quiz."""
    await state.set_state(QuizFlow.answering_question)
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
    header = f"❓ Вопрос {index + 1} из {total}\n\n"

    if q_type == "multiple_choice":
        text = header + q["question"]
        await message.answer(text, reply_markup=multiple_choice_keyboard(q["options"]))

    elif q_type == "true_false":
        text = header + q["question"]
        await message.answer(text, reply_markup=true_false_keyboard())

    elif q_type == "fill_blank":
        text = header + q["question"] + "\n\n✏️ Напиши ответ (пропущенное слово):"
        await message.answer(text, reply_markup=cancel_keyboard())

    elif q_type == "translation":
        text = header + q["question"] + "\n\n✏️ Напиши перевод:"
        await message.answer(text, reply_markup=cancel_keyboard())

    else:
        await state.update_data(current_index=index + 1)
        await _send_current_question(message, state)


@router.callback_query(QuizFlow.answering_question, F.data.startswith("ans:"))
async def answer_via_button(callback: CallbackQuery, state: FSMContext):
    """Handle answers from inline keyboard buttons."""
    user_answer = callback.data.split(":", 1)[1]
    await callback.answer()
    await _process_answer(callback.message, state, user_answer)


@router.message(QuizFlow.answering_question)
async def answer_via_text(message: Message, state: FSMContext):
    """Handle answers typed as text."""
    user_answer = message.text.strip() if message.text else ""
    if not user_answer:
        await message.answer("Напиши ответ текстом:")
        return
    await _process_answer(message, state, user_answer)


@router.callback_query(F.data == "cancel_quiz")
async def cancel_quiz(callback: CallbackQuery, state: FSMContext):
    """Cancel the current quiz and go home."""
    await state.clear()
    await callback.message.answer(
        "Тест отменён. Возвращаемся в меню.",
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

    q = questions[index]
    is_correct = check_answer(q, user_answer)

    if is_correct:
        correct_count += 1
        feedback = "✅ Правильно!"
    else:
        correct_display = q["correct"]
        if len(correct_display) == 1 and correct_display.upper() in "ABCD" and q.get("options"):
            idx = ord(correct_display.upper()) - ord("A")
            if 0 <= idx < len(q["options"]):
                correct_display = q["options"][idx]
        feedback = f"❌ Неправильно.\n\n📝 Правильный ответ: {correct_display}"
        explanation = q.get("explanation", "")
        if explanation:
            feedback += f"\n\n💡 {explanation}"

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
    )

    await message.answer(feedback)
    await _send_current_question(message, state)


async def _show_results(message: Message, state: FSMContext):
    """Show the final quiz results."""
    data = await state.get_data()
    language = data.get("language", "")
    topic = data.get("topic", "")
    total = data.get("question_count", 0)
    correct = data.get("correct_count", 0)
    answers = data.get("answers", [])

    actual_total = len(answers) or total
    percent = round(correct / actual_total * 100) if actual_total > 0 else 0

    if percent >= 90:
        emoji, comment = "🏆", "Отличный результат!"
    elif percent >= 70:
        emoji, comment = "👍", "Хороший результат!"
    elif percent >= 50:
        emoji, comment = "📖", "Неплохо, но есть над чем поработать."
    else:
        emoji, comment = "💪", "Нужно ещё потренироваться. Ты справишься!"

    lang_flag = "🇬🇧" if language == "English" else "🇪🇸"

    text = (
        f"📊 Результаты теста\n\n"
        f"{lang_flag} Язык: {language}\n"
        f"📚 Тема: {topic}\n\n"
        f"{emoji} Правильных: {correct} из {actual_total} ({percent}%)\n\n"
        f"{comment}"
    )

    try:
        from database.crud import save_test_session
        user_id = data.get("user_id")
        if user_id:
            await save_test_session(user_id, language, topic, actual_total, correct, percent, answers)
    except Exception:
        pass

    await state.clear()
    await message.answer(text, reply_markup=quiz_home_keyboard())
