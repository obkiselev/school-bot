from bot.config import LEVEL_DESCRIPTIONS


def build_test_prompt(language: str, topic: str, count: int, previous_questions: list[str] | None = None) -> str:
    level = LEVEL_DESCRIPTIONS.get(language, "5th grade student")

    if language == "English":
        source_lang, target_lang = "Russian", "English"
    else:
        source_lang, target_lang = "Russian", "Spanish"

    prompt = f"""You are an educational test generator for a 5th-grade student.

Language being tested: {language}
Student level: {level}
Topic: {topic}
Number of questions: {count}

Generate exactly {count} test questions. Mix the following question types for variety:
- multiple_choice: A question with 4 answer options. Exactly one is correct.
- fill_blank: A sentence with one word replaced by "___". The student must type the missing word.
- translation: A phrase or short sentence to translate from {source_lang} to {target_lang}.
- true_false: A statement that is either true or false about the language rule or vocabulary.

Rules:
1. Difficulty must be appropriate for a {level}.
2. All content must be related to the topic "{topic}".
3. For wrong answers in multiple_choice, make distractors plausible but clearly wrong.
4. For each question, provide a brief explanation (1-2 sentences) of why the correct answer is correct. Write explanations in Russian.
5. Output ONLY valid JSON array, no extra text before or after.
6. Ensure maximum variety: use different question types, different vocabulary items, and different sentence structures across all {count} questions. No two questions should test the same word or phrase.

Output format — JSON array of objects. Each object must have these fields:

For multiple_choice:
{{"type": "multiple_choice", "question": "Choose the correct form: She ___ to school every day.", "options": ["go", "goes", "going", "gone"], "correct": "goes", "explanation": "..."}}
IMPORTANT: "options" must contain the actual answer TEXT (words/phrases), NOT letters like A, B, C, D. Do NOT prefix options with "A)", "B)" etc. The field "correct" must be the EXACT text of one of the options.

For fill_blank:
{{"type": "fill_blank", "question": "I ___ to school every day.", "correct": "go", "explanation": "..."}}

For translation:
{{"type": "translation", "question": "Translate: Я люблю читать", "correct": "I like to read", "accept_also": ["I love reading", "I like reading"], "explanation": "..."}}

For true_false:
{{"type": "true_false", "question": "In Present Simple we add -s for 'they'.", "correct": "False", "explanation": "..."}}

Generate exactly {count} questions as a JSON array. Output ONLY the JSON array:"""

    if previous_questions:
        numbered = "\n".join(f"{i+1}. {q}" for i, q in enumerate(previous_questions))
        return prompt + f"""

IMPORTANT — DO NOT REPEAT THESE QUESTIONS.
The student has already seen these questions in previous tests. You MUST generate completely NEW and DIFFERENT questions. Do NOT reuse any of these:

{numbered}

Generate questions that test the same topic but use different words, sentences, and scenarios. Output ONLY the JSON array:"""

    return prompt
