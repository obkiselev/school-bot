"""Prompt templates for test generation."""
from config import settings


def build_test_prompt(language: str, topic: str, count: int, level: str = "A2", previous_questions: list[str] | None = None) -> str:
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

    if language in {"English", "French", "German"}:
        examples = f"""For multiple_choice:
{{"type": "multiple_choice", "question": "Choose the correct form: She ___ to school every day.", "options": ["go", "goes", "going", "gone"], "correct": "goes", "explanation": "..."}}
IMPORTANT: "options" must contain the actual answer TEXT (words/phrases), NOT letters like A, B, C, D. Do NOT prefix options with "A)", "B)" etc. The field "correct" must be the EXACT text of one of the options.

For fill_blank:
{{"type": "fill_blank", "question": "I ___ to school every day.", "correct": "go", "explanation": "..."}}

For translation:
{{"type": "translation", "question": "Translate: Я люблю читать", "correct": "I like to read", "accept_also": ["I love reading", "I like reading"], "explanation": "..."}}

For true_false:
{{"type": "true_false", "question": "In Present Simple we add -s for 'they'.", "correct": "False", "explanation": "..."}}"""
    elif language == "Spanish":
        examples = f"""For multiple_choice:
{{"type": "multiple_choice", "question": "Elige la forma correcta: Yo ___ en la escuela.", "options": ["estudio", "estudias", "estudia", "estudiamos"], "correct": "estudio", "explanation": "..."}}
IMPORTANT: "options" must contain the actual answer TEXT (words/phrases), NOT letters like A, B, C, D. Do NOT prefix options with "A)", "B)" etc. The field "correct" must be the EXACT text of one of the options.

For fill_blank:
{{"type": "fill_blank", "question": "Mi madre ___ en una oficina.", "correct": "trabaja", "explanation": "..."}}

For translation:
{{"type": "translation", "question": "Translate: Моя семья", "correct": "Mi familia", "accept_also": ["La familia mía"], "explanation": "..."}}

For true_false:
{{"type": "true_false", "question": "In Spanish, nouns have gender (masculine/feminine).", "correct": "True", "explanation": "..."}}"""
    else:
        examples = """For multiple_choice:
{"type": "multiple_choice", "question": "Чему равен периметр квадрата со стороной 3 см?", "options": ["6 см", "9 см", "12 см", "15 см"], "correct": "12 см", "explanation": "..."}
IMPORTANT: "options" must contain actual answer TEXT, not letters.

For fill_blank:
{"type": "fill_blank", "question": "Процесс деления клетки называется ___ .", "correct": "митоз", "explanation": "..."}

For true_false:
{"type": "true_false", "question": "В XIX веке Наполеон вторгся в Россию.", "correct": "True", "explanation": "..."}

For matching:
{"type": "matching", "question": "Сопоставь термин и определение: клетка — ...", "correct": "клетка:структурная единица", "accept_also": ["клетка - структурная единица"], "explanation": "..."}

For audio:
{"type": "audio", "question": "Прослушай и ответь: какой орган отвечает за дыхание?", "audio_text": "Лёгкие", "correct": "лёгкие", "accept_also": ["легкие"], "explanation": "..."}"""

    translation_rule = (
        f"- translation: A phrase or short sentence to translate from {source_lang} to {target_lang}."
        if translation_allowed
        else "- translation questions are optional and usually should not be used for this subject."
    )

    prompt = f"""You are an educational test generator.

Language being tested: {language}
Student level: {level} — {level_desc}
Topic: {topic}
Number of questions: {count}

Generate exactly {count} test questions for {language}. Mix the following question types for variety:
- multiple_choice: A question with 4 answer options. Exactly one is correct.
- fill_blank: A sentence with one word replaced by "___". The student must type the missing word.
- true_false: A statement that is either true or false about the language rule or vocabulary.
- matching: A simple matching task, student answers with one text line.
- audio: Short listening-style question (you may include "audio_text" field with transcript).
{translation_rule}

Rules:
1. Difficulty must be appropriate for a {level} ({level_desc}) student.
2. All content must be related to the topic "{topic}".
3. All questions and answer options MUST be in {content_language} (except translations from {source_lang}, if used).
4. For wrong answers in multiple_choice, make distractors plausible but clearly wrong.
5. For each question, provide a brief explanation (1-2 sentences) of why the correct answer is correct. Write explanations in Russian.
6. Output ONLY valid JSON array, no extra text before or after.
7. Ensure maximum variety: use different question types, different vocabulary items, and different sentence structures across all {count} questions. No two questions should test the same word or phrase.

Output format — JSON array of objects. Each object must have these fields:

{examples}

Generate exactly {count} questions as a JSON array. Output ONLY the JSON array:"""

    if previous_questions:
        numbered = "\n".join(f"{i+1}. {q}" for i, q in enumerate(previous_questions))
        return prompt + f"""

IMPORTANT — DO NOT REPEAT THESE QUESTIONS.
The student has already seen these questions in previous tests. You MUST generate completely NEW and DIFFERENT questions. Do NOT reuse any of these:

{numbered}

Generate questions that test the same topic but use different words, sentences, and scenarios. Output ONLY the JSON array:"""

    return prompt
