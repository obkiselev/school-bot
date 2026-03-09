"""Template-based quiz fallback when LLM endpoints are unavailable."""
from copy import deepcopy


_ENGLISH_POOL: list[dict] = [
    {
        "type": "multiple_choice",
        "question": "Choose the correct form: She ___ to school every day.",
        "options": ["go", "goes", "going", "gone"],
        "correct": "goes",
        "explanation": "For she/he/it in Present Simple, add -s.",
    },
    {
        "type": "fill_blank",
        "question": "My best friend ___ from Moscow.",
        "correct": "is",
        "explanation": "Use 'is' with singular subject in this sentence.",
    },
    {
        "type": "translation",
        "question": "Translate: ? ????? ????? ?????? ?????.",
        "correct": "I read a book every evening.",
        "accept_also": ["I read a book every night."],
        "explanation": "This is a regular action, so Present Simple is used.",
    },
    {
        "type": "true_false",
        "question": "In Present Simple questions we often use do/does.",
        "correct": "True",
        "explanation": "This is a core grammar rule of Present Simple.",
    },
    {
        "type": "multiple_choice",
        "question": "Choose the correct option: They ___ football on Sundays.",
        "options": ["plays", "play", "is playing", "played"],
        "correct": "play",
        "explanation": "With 'they' use the base verb form in Present Simple.",
    },
    {
        "type": "multiple_choice",
        "question": "Choose the correct article: I saw ___ elephant at the zoo.",
        "options": ["a", "an", "the", "-"],
        "correct": "an",
        "explanation": "Use 'an' before words that start with a vowel sound.",
    },
    {
        "type": "fill_blank",
        "question": "Yesterday we ___ a very interesting film.",
        "correct": "watched",
        "explanation": "The sentence is in Past Simple, so use the past form.",
    },
    {
        "type": "translation",
        "question": "Translate: Она обычно встает в семь утра.",
        "correct": "She usually gets up at seven in the morning.",
        "accept_also": ["She usually gets up at 7 in the morning."],
        "explanation": "Use Present Simple for habitual actions.",
    },
    {
        "type": "true_false",
        "question": "In English, adjectives usually come before nouns.",
        "correct": "True",
        "explanation": "For example: a big house, an interesting book.",
    },
    {
        "type": "multiple_choice",
        "question": "Choose the correct form: We ___ dinner right now.",
        "options": ["have", "having", "are having", "had"],
        "correct": "are having",
        "explanation": "Use Present Continuous for actions happening now.",
    },
]

_SPANISH_POOL: list[dict] = [
    {
        "type": "multiple_choice",
        "question": "Elige la forma correcta: Yo ___ en la escuela.",
        "options": ["estudio", "estudias", "estudia", "estudiamos"],
        "correct": "estudio",
        "explanation": "Con 'yo' se usa la forma 'estudio'.",
    },
    {
        "type": "fill_blank",
        "question": "Mi madre ___ en una oficina.",
        "correct": "trabaja",
        "explanation": "Para 'mi madre' se usa la forma de tercera persona singular.",
    },
    {
        "type": "translation",
        "question": "Translate: ? ???? ???? ???????? ???????.",
        "correct": "Tengo tarea.",
        "accept_also": ["Yo tengo tarea."],
        "explanation": "The verb 'tener' in first person is 'tengo'.",
    },
    {
        "type": "true_false",
        "question": "In Spanish, nouns usually have grammatical gender.",
        "correct": "True",
        "explanation": "Spanish nouns are usually masculine or feminine.",
    },
    {
        "type": "multiple_choice",
        "question": "Elige la opcion correcta: Nosotros ___ espanol en clase.",
        "options": ["hablo", "hablas", "hablamos", "habla"],
        "correct": "hablamos",
        "explanation": "Con 'nosotros' se usa la forma 'hablamos'.",
    },
]

_FRENCH_POOL: list[dict] = [
    {
        "type": "multiple_choice",
        "question": "Choisis la bonne forme: Je ___ eleve.",
        "options": ["suis", "es", "est", "sommes"],
        "correct": "suis",
        "explanation": "Avec 'je' on utilise 'suis'.",
    },
    {
        "type": "fill_blank",
        "question": "Nous ___ au college.",
        "correct": "sommes",
        "explanation": "Avec 'nous' le verbe etre est 'sommes'.",
    },
    {
        "type": "true_false",
        "question": "En francais, les noms ont un genre.",
        "correct": "True",
        "explanation": "Les noms francais sont masculins ou feminins.",
    },
]

_GERMAN_POOL: list[dict] = [
    {
        "type": "multiple_choice",
        "question": "Wahle die richtige Form: Ich ___ Schuler.",
        "options": ["bin", "bist", "ist", "sind"],
        "correct": "bin",
        "explanation": "Mit 'ich' verwendet man 'bin'.",
    },
    {
        "type": "fill_blank",
        "question": "Wir ___ heute in der Schule.",
        "correct": "sind",
        "explanation": "Mit 'wir' ist die Form von 'sein' = sind.",
    },
    {
        "type": "true_false",
        "question": "Im Deutschen gibt es vier Falle.",
        "correct": "True",
        "explanation": "Nominativ, Akkusativ, Dativ, Genitiv.",
    },
]

_MATH_POOL: list[dict] = [
    {
        "type": "multiple_choice",
        "question": "Chemu raven perimetr kvadrata so storonoi 4 sm?",
        "options": ["8 sm", "12 sm", "16 sm", "20 sm"],
        "correct": "16 sm",
        "explanation": "Perimeter of a square is 4 multiplied by side length.",
    },
    {
        "type": "fill_blank",
        "question": "7 * 8 = ___",
        "correct": "56",
        "explanation": "Basic multiplication table.",
    },
    {
        "type": "true_false",
        "question": "Sum of triangle angles equals 180 degrees.",
        "correct": "True",
        "explanation": "This is a standard Euclidean geometry rule.",
    },
    {
        "type": "multiple_choice",
        "question": "What is 25% of 200?",
        "options": ["25", "40", "50", "75"],
        "correct": "50",
        "explanation": "25% equals one quarter.",
    },
]

_HISTORY_POOL: list[dict] = [
    {
        "type": "true_false",
        "question": "The Patriotic War against Napoleon in Russia started in 1812.",
        "correct": "True",
        "explanation": "The 1812 campaign is called the Patriotic War in Russia.",
    },
    {
        "type": "multiple_choice",
        "question": "Which city was the political center of ancient Rus?",
        "options": ["Kiev", "Moscow", "Novgorod", "Pskov"],
        "correct": "Kiev",
        "explanation": "Kiev was a key center in the early period.",
    },
    {
        "type": "fill_blank",
        "question": "The first Russian emperor was ___ I.",
        "correct": "Peter",
        "explanation": "Peter I accepted the imperial title in 1721.",
    },
    {
        "type": "multiple_choice",
        "question": "Which event happened earlier?",
        "options": [
            "Christianization of Rus",
            "Mongol invasion",
            "Reforms of Peter I",
            "Abolition of serfdom",
        ],
        "correct": "Christianization of Rus",
        "explanation": "It happened in the 10th century.",
    },
]

_BIOLOGY_POOL: list[dict] = [
    {
        "type": "true_false",
        "question": "A cell is the structural unit of living organisms.",
        "correct": "True",
        "explanation": "This is a core biology definition.",
    },
    {
        "type": "multiple_choice",
        "question": "Which organ pumps blood through the body?",
        "options": ["Liver", "Heart", "Kidneys", "Lungs"],
        "correct": "Heart",
        "explanation": "The heart pumps blood through vessels.",
    },
    {
        "type": "fill_blank",
        "question": "The process of making organic substances using light is called ___.",
        "correct": "photosynthesis",
        "explanation": "Photosynthesis occurs in chloroplasts.",
    },
    {
        "type": "true_false",
        "question": "Mitochondria are involved in cellular respiration.",
        "correct": "True",
        "explanation": "Mitochondria are the main ATP production site.",
    },
]


def _subject_pool(language: str) -> list[dict]:
    if language == "Mathematics":
        return _MATH_POOL
    if language == "History":
        return _HISTORY_POOL
    if language == "Biology":
        return _BIOLOGY_POOL
    return _ENGLISH_POOL


def _apply_variant(item: dict, variant_no: int) -> dict:
    """Avoid exact duplicate question texts when count > pool size."""
    if variant_no <= 1:
        return item
    out = deepcopy(item)
    out["question"] = f"{out['question']} (variant {variant_no})"
    if out.get("audio_text"):
        out["audio_text"] = f"{out['audio_text']} (v{variant_no})"
    return out


def generate_fallback_test(language: str, topic: str, count: int, level: str = "A2") -> list[dict]:
    """Build a deterministic fallback quiz with expected schema."""
    if language == "English":
        pool = _ENGLISH_POOL
    elif language == "Spanish":
        pool = _SPANISH_POOL
    elif language == "French":
        pool = _FRENCH_POOL
    elif language == "German":
        pool = _GERMAN_POOL
    elif language in {"Mathematics", "History", "Biology"}:
        pool = _subject_pool(language)
    else:
        pool = _ENGLISH_POOL

    result: list[dict] = []
    for idx in range(count):
        base_idx = idx % len(pool)
        variant_no = idx // len(pool) + 1
        item = _apply_variant(deepcopy(pool[base_idx]), variant_no)
        item["question"] = f"[Fallback | {level} | {topic}] {item['question']}"
        result.append(item)

    return result
