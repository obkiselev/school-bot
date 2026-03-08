"""Template-based quiz fallback when LLM endpoints are unavailable."""
from copy import deepcopy


_ENGLISH_POOL: list[dict] = [
    {
        "type": "multiple_choice",
        "question": "Choose the correct form: She ___ to school every day.",
        "options": ["go", "goes", "going", "gone"],
        "correct": "goes",
        "explanation": "Для she/he/it в Present Simple добавляется -s.",
    },
    {
        "type": "fill_blank",
        "question": "My best friend ___ from Moscow.",
        "correct": "is",
        "explanation": "С подлежащим в единственном числе используем форму is.",
    },
    {
        "type": "translation",
        "question": "Translate: Я читаю книгу каждый вечер.",
        "correct": "I read a book every evening.",
        "accept_also": ["I read a book every night."],
        "explanation": "В регулярных действиях используется Present Simple.",
    },
    {
        "type": "true_false",
        "question": "In Present Simple questions we often use do/does.",
        "correct": "True",
        "explanation": "Это базовое правило построения вопросов в Present Simple.",
    },
    {
        "type": "multiple_choice",
        "question": "Choose the correct option: They ___ football on Sundays.",
        "options": ["plays", "play", "is playing", "played"],
        "correct": "play",
        "explanation": "С they в Present Simple используется базовая форма глагола.",
    },
]

_SPANISH_POOL: list[dict] = [
    {
        "type": "multiple_choice",
        "question": "Elige la forma correcta: Yo ___ en la escuela.",
        "options": ["estudio", "estudias", "estudia", "estudiamos"],
        "correct": "estudio",
        "explanation": "С местоимением yo используется форма estudio.",
    },
    {
        "type": "fill_blank",
        "question": "Mi madre ___ en una oficina.",
        "correct": "trabaja",
        "explanation": "Для ella (mi madre) в Presente используется trabaja.",
    },
    {
        "type": "translation",
        "question": "Translate: У меня есть домашнее задание.",
        "correct": "Tengo tarea.",
        "accept_also": ["Yo tengo tarea."],
        "explanation": "Глагол tener в 1 лице: tengo.",
    },
    {
        "type": "true_false",
        "question": "In Spanish, nouns usually have grammatical gender.",
        "correct": "True",
        "explanation": "Существительные в испанском обычно мужского или женского рода.",
    },
    {
        "type": "multiple_choice",
        "question": "Elige la opción correcta: Nosotros ___ español en clase.",
        "options": ["hablo", "hablas", "hablamos", "habla"],
        "correct": "hablamos",
        "explanation": "С nosotros используется форма hablamos.",
    },
]

_FRENCH_POOL: list[dict] = [
    {
        "type": "multiple_choice",
        "question": "Choisis la bonne forme: Je ___ élève.",
        "options": ["suis", "es", "est", "sommes"],
        "correct": "suis",
        "explanation": "С местоимением je используется suis.",
    },
    {
        "type": "fill_blank",
        "question": "Nous ___ au collège.",
        "correct": "sommes",
        "explanation": "Для nous глагол être: sommes.",
    },
    {
        "type": "true_false",
        "question": "En français, les noms ont un genre.",
        "correct": "True",
        "explanation": "Во французском у существительных есть род.",
    },
]

_GERMAN_POOL: list[dict] = [
    {
        "type": "multiple_choice",
        "question": "Wähle die richtige Form: Ich ___ Schüler.",
        "options": ["bin", "bist", "ist", "sind"],
        "correct": "bin",
        "explanation": "С местоимением ich используется bin.",
    },
    {
        "type": "fill_blank",
        "question": "Wir ___ heute in der Schule.",
        "correct": "sind",
        "explanation": "Для wir глагол sein: sind.",
    },
    {
        "type": "true_false",
        "question": "Im Deutschen gibt es vier Fälle.",
        "correct": "True",
        "explanation": "В немецком действительно четыре падежа.",
    },
]

_SCHOOL_POOL: list[dict] = [
    {
        "type": "multiple_choice",
        "question": "Чему равен периметр квадрата со стороной 4 см?",
        "options": ["8 см", "12 см", "16 см", "20 см"],
        "correct": "16 см",
        "explanation": "Периметр квадрата: 4 * сторона.",
    },
    {
        "type": "true_false",
        "question": "Клетка — структурная единица живого организма.",
        "correct": "True",
        "explanation": "Это базовое определение в биологии.",
    },
    {
        "type": "matching",
        "question": "Сопоставь: столица Франции — ___",
        "correct": "париж",
        "accept_also": ["Париж"],
        "explanation": "Столица Франции — Париж.",
    },
    {
        "type": "audio",
        "question": "Прослушай подсказку и назови орган дыхательной системы.",
        "audio_text": "Этот орган парный и находится в грудной клетке.",
        "correct": "лёгкие",
        "accept_also": ["легкие"],
        "explanation": "Речь о лёгких.",
    },
]


def generate_fallback_test(language: str, topic: str, count: int, level: str = "A2") -> list[dict]:
    """Build a deterministic fallback quiz with the expected schema."""
    if language == "English":
        pool = _ENGLISH_POOL
    elif language == "Spanish":
        pool = _SPANISH_POOL
    elif language == "French":
        pool = _FRENCH_POOL
    elif language == "German":
        pool = _GERMAN_POOL
    elif language in {"Mathematics", "History", "Biology"}:
        pool = _SCHOOL_POOL
    else:
        pool = _ENGLISH_POOL
    result: list[dict] = []

    for idx in range(count):
        item = deepcopy(pool[idx % len(pool)])
        item["question"] = f"[Fallback | {level} | {topic}] {item['question']}"
        result.append(item)

    return result
