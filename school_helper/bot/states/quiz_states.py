from aiogram.fsm.state import StatesGroup, State


class QuizFlow(StatesGroup):
    choosing_language = State()
    choosing_topic = State()
    entering_custom_topic = State()
    choosing_question_count = State()
    generating_test = State()
    answering_question = State()
    answering_matching_sub = State()
    viewing_results = State()
