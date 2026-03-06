"""Format quiz history and statistics."""
from database.crud import get_user_sessions, get_weak_topics, get_stats_summary


async def format_history(user_id: int) -> str:
    """Format recent test history as a readable text."""
    sessions = await get_user_sessions(user_id)

    if not sessions:
        return "📭 Ты ещё не проходил тесты. Начни первый тест!"

    lines = ["📋 Последние тесты:\n"]
    for s in sessions:
        lang_flag = "🇬🇧" if s["language"] == "English" else "🇪🇸"
        score = round(s["score_percent"])
        lines.append(
            f"{lang_flag} {s['topic']} — {s['correct_answers']}/{s['total_questions']} ({score}%)"
        )

    return "\n".join(lines)


async def format_weak_areas(user_id: int) -> str:
    """Format weak topics as a readable text."""
    weak = await get_weak_topics(user_id)

    if not weak:
        return ""

    lines = ["\n⚠️ Темы, которые нужно подтянуть:\n"]
    for w in weak:
        lang_flag = "🇬🇧" if w["language"] == "English" else "🇪🇸"
        avg = round(w["avg_score"])
        lines.append(f"{lang_flag} {w['topic']} — средний балл {avg}%")

    return "\n".join(lines)


async def format_overall_stats(user_id: int) -> str:
    """Format overall statistics."""
    stats = await get_stats_summary(user_id)

    if not stats or not stats.get("total_tests"):
        return ""

    avg = round(stats.get("avg_score") or 0)
    return (
        f"\n📊 Общая статистика:\n"
        f"Тестов пройдено: {stats['total_tests']}\n"
        f"Вопросов всего: {stats['total_questions_answered']}\n"
        f"Правильных ответов: {stats['total_correct']}\n"
        f"Средний балл: {avg}%"
    )
