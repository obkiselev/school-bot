"""Template-based fallback questions when LLM is unavailable."""

ENGLISH_PAIRS = [
    ("школа", "school"),
    ("книга", "book"),
    ("учитель", "teacher"),
    ("домашнее задание", "homework"),
    ("друг", "friend"),
    ("яблоко", "apple"),
    ("вода", "water"),
    ("город", "city"),
]

SPANISH_PAIRS = [
    ("школа", "escuela"),
    ("книга", "libro"),
    ("учитель", "profesor"),
    ("домашнее задание", "tarea"),
    ("друг", "amigo"),
    ("яблоко", "manzana"),
    ("вода", "agua"),
    ("город", "ciudad"),
]


def generate_fallback_questions(language: str, topic: str, count: int) -> list[dict]:
    """Generate deterministic backup questions for quiz flow."""
    if count <= 0:
        return []

    bank = ENGLISH_PAIRS if language == "English" else SPANISH_PAIRS
    result: list[dict] = []

    for i in range(count):
        q_type = i % 4
        pair = bank[i % len(bank)]
        next_pair = bank[(i + 1) % len(bank)]
        alt_pair_2 = bank[(i + 2) % len(bank)]
        alt_pair_3 = bank[(i + 3) % len(bank)]
        ru_word, target_word = pair

        if q_type == 0:
            options = [target_word, next_pair[1], alt_pair_2[1], alt_pair_3[1]]
            question = (
                f"Choose the correct translation for '{ru_word}' "
                if language == "English"
                else f"Elige la traduccion correcta para '{ru_word}' "
            )
            result.append({
                "type": "multiple_choice",
                "question": f"{question}(topic: {topic}).",
                "options": options,
                "correct": target_word,
                "explanation": "Резервный шаблонный вопрос: выбери правильный перевод.",
            })
            continue

        if q_type == 1:
            if language == "English":
                sentence = f"I need this ___ for my lesson about {topic}."
            else:
                sentence = f"Necesito este ___ para mi clase sobre {topic}."
            result.append({
                "type": "fill_blank",
                "question": sentence,
                "correct": target_word,
                "explanation": "Резервный шаблонный вопрос: вставь слово по смыслу.",
            })
            continue

        if q_type == 2:
            if language == "English":
                q_text = f"Translate: {ru_word}"
            else:
                q_text = f"Translate: {ru_word}"
            result.append({
                "type": "translation",
                "question": q_text,
                "correct": target_word,
                "explanation": "Резервный шаблонный вопрос: прямой перевод слова.",
            })
            continue

        is_true = (i % 2 == 0)
        shown_translation = target_word if is_true else next_pair[1]
        if language == "English":
            tf_question = f"The word '{ru_word}' translates as '{shown_translation}'."
        else:
            tf_question = f"La palabra '{ru_word}' se traduce como '{shown_translation}'."
        result.append({
            "type": "true_false",
            "question": f"{tf_question} Topic: {topic}.",
            "correct": "True" if is_true else "False",
            "explanation": "Резервный шаблонный вопрос: проверь соответствие перевода.",
        })

    return result
