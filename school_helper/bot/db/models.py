from typing import TypedDict


class AnswerRecord(TypedDict):
    question_type: str
    question_text: str
    correct_answer: str
    user_answer: str
    is_correct: bool
    explanation: str


class SessionSummary(TypedDict):
    id: int
    language: str
    topic: str
    total_questions: int
    correct_answers: int
    score_percent: float
    finished_at: str
