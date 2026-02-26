from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.states.quiz_states import QuizFlow
from bot.services.answer_checker import check_answer
from bot.keyboards.quiz_kb import multiple_choice_keyboard, true_false_keyboard, cancel_keyboard
from bot.keyboards.main_menu import main_menu_keyboard

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
        # No more questions — show results
        from bot.handlers.results import show_results
        await show_results(message, state)
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
        # Unknown type — skip
        await state.update_data(current_index=index + 1)
        await _send_current_question(message, state)


@router.callback_query(QuizFlow.answering_question, F.data.startswith("ans:"))
async def answer_via_button(callback: CallbackQuery, state: FSMContext):
    """Handle answers from inline keyboard buttons (multiple_choice, true_false)."""
    user_answer = callback.data.split(":", 1)[1]
    await callback.answer()
    await _process_answer(callback.message, state, user_answer)


@router.message(QuizFlow.answering_question)
async def answer_via_text(message: Message, state: FSMContext):
    """Handle answers typed as text (fill_blank, translation)."""
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
        "Тест отменён. Возвращаемся в главное меню.",
        reply_markup=main_menu_keyboard(),
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

    # Build feedback message
    if is_correct:
        correct_count += 1
        feedback = "✅ Правильно!"
    else:
        correct_display = q["correct"]
        # If correct is a single letter, try to resolve from options
        if len(correct_display) == 1 and correct_display.upper() in "ABCD" and q.get("options"):
            idx = ord(correct_display.upper()) - ord("A")
            if 0 <= idx < len(q["options"]):
                correct_display = q["options"][idx]
        feedback = f"❌ Неправильно.\n\n📝 Правильный ответ: {correct_display}"
        explanation = q.get("explanation", "")
        if explanation:
            feedback += f"\n\n💡 {explanation}"

    # Save answer record
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
