import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5-7b-instruct")
DB_PATH = os.getenv("DB_PATH", "data/school_helper.db")

TOPICS = {
    "English": [
        "Present Simple and Present Continuous",
        "Past Simple",
        "Vocabulary: School and Daily Life",
        "Vocabulary: Family, Hobbies, and Travel",
        "Reading Comprehension: Short Texts",
    ],
    "Spanish": [
        "Basic Vocabulary: Colors, Numbers, Days of the Week",
        "Family and School Vocabulary",
        "Present Tense: Regular Verbs (-ar, -er, -ir)",
        "Greetings and Basic Phrases",
        "Food and Animals Vocabulary",
    ],
}

LEVEL_DESCRIPTIONS = {
    "English": "5th grader studying English for the 5th year (intermediate level, knows basic tenses and vocabulary)",
    "Spanish": "5th grader studying Spanish for the 1st year (complete beginner, basic vocabulary and simple present tense only)",
}

QUESTION_COUNTS = [5, 10, 15, 20]
