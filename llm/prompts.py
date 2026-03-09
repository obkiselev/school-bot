"""Prompt templates for test generation."""
from config import settings


def _examples_for_language(language: str) -> str:
    if language in {"English", "French", "German"}:
        return """For multiple_choice:
{"type": "multiple_choice", "question": "Choose the correct form: She ___ to school every day.", "options": ["go", "goes", "going", "gone"], "correct": "goes", "explanation": "..."}
IMPORTANT: "options" must contain answer text (words/phrases), not A/B/C/D labels.

For fill_blank:
{"type": "fill_blank", "question": "I ___ to school every day.", "correct": "go", "explanation": "..."}

For translation:
{"type": "translation", "question": "Translate: Я люблю читать.", "correct": "I like reading", "accept_also": ["I love reading"], "explanation": "..."}

For true_false:
{"type": "true_false", "question": "In Present Simple we add -s for 'they'.", "correct": "False", "explanation": "..."}"""

    if language == "Spanish":
        return """For multiple_choice:
{"type": "multiple_choice", "question": "Elige la forma correcta: Yo ___ en la escuela.", "options": ["estudio", "estudias", "estudia", "estudiamos"], "correct": "estudio", "explanation": "..."}
IMPORTANT: "options" must contain answer text (words/phrases), not A/B/C/D labels.

For fill_blank:
{"type": "fill_blank", "question": "Mi madre ___ en una oficina.", "correct": "trabaja", "explanation": "..."}

For translation:
{"type": "translation", "question": "Translate: Моя семья.", "correct": "Mi familia", "accept_also": ["La familia mia"], "explanation": "..."}

For true_false:
{"type": "true_false", "question": "In Spanish, nouns have gender (masculine/feminine).", "correct": "True", "explanation": "..."}"""

    if language == "Mathematics":
        return """For multiple_choice:
{"type": "multiple_choice", "question": "Чему равен периметр квадрата со стороной 6 см?", "options": ["12 см", "18 см", "24 см", "36 см"], "correct": "24 см", "explanation": "..."}
IMPORTANT: "options" must contain answer text (numbers/words), not A/B/C/D labels.

For fill_blank:
{"type": "fill_blank", "question": "9 * 7 = ___", "correct": "63", "explanation": "..."}

For true_false:
{"type": "true_false", "question": "Сумма углов треугольника равна 180 градусам.", "correct": "True", "explanation": "..."}"""

    if language == "History":
        return """For multiple_choice:
{"type": "multiple_choice", "question": "В каком году началась Отечественная война 1812 года?", "options": ["1805", "1812", "1825", "1914"], "correct": "1812", "explanation": "..."}
IMPORTANT: "options" must contain answer text, not A/B/C/D labels.

For fill_blank:
{"type": "fill_blank", "question": "Первым российским императором был ___ I.", "correct": "Петр", "explanation": "..."}

For true_false:
{"type": "true_false", "question": "Крещение Руси произошло раньше монгольского нашествия.", "correct": "True", "explanation": "..."}"""

    if language == "Biology":
        return """For multiple_choice:
{"type": "multiple_choice", "question": "Какой орган перекачивает кровь по организму?", "options": ["Печень", "Сердце", "Почки", "Легкие"], "correct": "Сердце", "explanation": "..."}
IMPORTANT: "options" must contain answer text, not A/B/C/D labels.

For fill_blank:
{"type": "fill_blank", "question": "Процесс образования органических веществ на свету называется ___.", "correct": "фотосинтез", "explanation": "..."}

For true_false:
{"type": "true_false", "question": "Клетка является структурной единицей живых организмов.", "correct": "True", "explanation": "..."}"""

    return """For multiple_choice:
{"type": "multiple_choice", "question": "Выбери правильный вариант ответа по теме.", "options": ["вариант 1", "вариант 2", "вариант 3", "вариант 4"], "correct": "вариант 1", "explanation": "..."}
IMPORTANT: "options" must contain answer text, not A/B/C/D labels.

For fill_blank:
{"type": "fill_blank", "question": "Заполни пропуск: ___", "correct": "ответ", "explanation": "..."}

For true_false:
{"type": "true_false", "question": "Утверждение по теме.", "correct": "True", "explanation": "..."}"""


def build_test_prompt(
    language: str,
    topic: str,
    count: int,
    level: str = "A2",
    previous_questions: list[str] | None = None,
) -> str:
    level_desc = settings.LEVEL_DESCRIPTIONS.get(level, f"{level} level student")

    source_target = {
        "English": ("Russian", "English"),
        "Spanish": ("Russian", "Spanish"),
        "French": ("Russian", "French"),
        "German": ("Russian", "German"),
    }
    source_lang, target_lang = source_target.get(language, ("Russian", "Russian"))
    translation_allowed = language in source_target
    content_language = language if translation_allowed else "Russian"

    translation_rule = (
        f"- translation: A phrase or short sentence to translate from {source_lang} to {target_lang}."
        if translation_allowed
        else "- translation questions are optional and usually should not be used for this subject."
    )
    subject_rule = (
        f"8. This test is strictly for {language}. Do not include content from other subjects/languages."
    )

    examples = _examples_for_language(language)

    prompt = f"""You are an educational test generator.

Language being tested: {language}
Student level: {level} - {level_desc}
Topic: {topic}
Number of questions: {count}

Generate exactly {count} test questions for {language}. Mix the following question types for variety:
- multiple_choice: A question with 4 answer options. Exactly one is correct.
- fill_blank: A sentence with one word replaced by "___". The student must type the missing word.
- true_false: A statement that is either true or false.
- matching: A simple matching task, student answers with one text line.
- audio: Short listening-style question (you may include "audio_text" field with transcript).
{translation_rule}

Rules:
1. Difficulty must be appropriate for a {level} ({level_desc}) student.
2. All content must be related to the topic "{topic}".
3. All questions and options MUST be in {content_language} (except translations from {source_lang}, if used).
4. For wrong answers in multiple_choice, make distractors plausible but clearly wrong.
5. For each question, provide a brief explanation (1-2 sentences) in Russian.
6. Output ONLY a valid JSON array, no extra text before or after.
7. Ensure maximum variety: no repeated words/sentences.
{subject_rule}

Output format - JSON array of objects. Each object must follow examples:

{examples}

Generate exactly {count} questions as a JSON array. Output ONLY the JSON array:"""

    if previous_questions:
        numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(previous_questions))
        return prompt + f"""

IMPORTANT - DO NOT REPEAT THESE QUESTIONS.
The student has already seen these questions in previous tests. You MUST generate completely NEW questions:

{numbered}

Output ONLY the JSON array:"""

    return prompt
