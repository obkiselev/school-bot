"""Сервис аналитики оценок — средние баллы, тренды, распределение."""
import html
from collections import defaultdict
from datetime import date, timedelta
from math import floor
from typing import Dict, List, Optional, Tuple

from mesh_api.models import Grade

# Порог для определения тренда (разница средних)
_TREND_THRESHOLD = 0.3

# Лимит длины сообщения Telegram
_MAX_MESSAGE_LEN = 3800


# ============================================================================
# ПАРСИНГ ОЦЕНОК
# ============================================================================

def parse_grade_value(value: str) -> Optional[float]:
    """Конвертирует строковую оценку в числовую.

    "5" -> 5.0, "4" -> 4.0, "3" -> 3.0, "2" -> 2.0, "1" -> 1.0
    "зачет", "н", "незачет", "" -> None
    """
    try:
        num = int(value)
        if 1 <= num <= 5:
            return float(num)
        return None
    except (ValueError, TypeError):
        return None


# ============================================================================
# ВЫЧИСЛЕНИЯ
# ============================================================================

def compute_subject_averages(grades: List[Grade]) -> Dict[str, float]:
    """Средний балл по каждому предмету. Нечисловые оценки пропускаются."""
    by_subject: Dict[str, List[float]] = defaultdict(list)

    for grade in grades:
        num = parse_grade_value(grade.grade_value)
        if num is not None:
            by_subject[grade.subject].append(num)

    return {
        subj: round(sum(vals) / len(vals), 2)
        for subj, vals in by_subject.items()
        if vals
    }


def compute_overall_average(grades: List[Grade]) -> Optional[float]:
    """Общий средний балл по всем оценкам."""
    numeric = [
        parse_grade_value(g.grade_value)
        for g in grades
    ]
    numeric = [n for n in numeric if n is not None]

    if not numeric:
        return None

    return round(sum(numeric) / len(numeric), 2)


def compute_trends(
    current_averages: Dict[str, float],
    previous_averages: Dict[str, float],
) -> Dict[str, str]:
    """Определяет тренд по каждому предмету: рост/падение/стабильно.

    Returns:
        {"Математика": "up", "Физика": "down", "Химия": "stable", "Биология": "new"}
    """
    trends = {}

    for subject, current_avg in current_averages.items():
        if subject not in previous_averages:
            trends[subject] = "new"
        else:
            diff = current_avg - previous_averages[subject]
            if diff > _TREND_THRESHOLD:
                trends[subject] = "up"
            elif diff < -_TREND_THRESHOLD:
                trends[subject] = "down"
            else:
                trends[subject] = "stable"

    return trends


def compute_grade_distribution(grades: List[Grade]) -> Dict[int, int]:
    """Распределение оценок: {5: 8, 4: 7, 3: 4, 2: 1}."""
    dist: Dict[int, int] = {}

    for grade in grades:
        num = parse_grade_value(grade.grade_value)
        if num is not None:
            key = int(num)
            dist[key] = dist.get(key, 0) + 1

    return dist


# ============================================================================
# ПЕРИОДЫ
# ============================================================================

def get_analytics_periods(period: str) -> Tuple[Tuple[date, date], Tuple[date, date]]:
    """Возвращает даты текущего и предыдущего периода для сравнения.

    Returns:
        ((current_from, current_to), (previous_from, previous_to))
    """
    today = date.today()

    if period == "month":
        days = 30
    elif period == "quarter":
        days = 90
    else:  # week
        days = 7

    current_from = today - timedelta(days=days - 1)
    current_to = today

    previous_to = current_from - timedelta(days=1)
    previous_from = previous_to - timedelta(days=days - 1)

    return (current_from, current_to), (previous_from, previous_to)


def get_period_label(period: str) -> str:
    """Человекочитаемое название периода."""
    labels = {
        "week": "за неделю",
        "month": "за месяц",
        "quarter": "за четверть",
    }
    return labels.get(period, "за неделю")


# ============================================================================
# ФОРМАТИРОВАНИЕ
# ============================================================================

_TREND_ICONS = {
    "up": "\u2197\ufe0f",      # ↗️
    "down": "\u2198\ufe0f",    # ↘️
    "stable": "\u27a1\ufe0f",  # ➡️
    "new": "\U0001f195",       # 🆕
}

_TREND_LABELS = {
    "up": "рост",
    "down": "падение",
    "stable": "стабильно",
    "new": "новый",
}

_GRADE_ICONS = {
    5: "\u2b50",  # ⭐
    4: "\u2705",  # ✅
    3: "\U0001f4dd",  # 📝
    2: "\u26a0\ufe0f",  # ⚠️
    1: "\U0001f6a8",  # 🚨
}


def format_analytics(
    current_grades: List[Grade],
    previous_grades: List[Grade],
    period: str,
) -> str:
    """Форматирует полное аналитическое сообщение в HTML."""
    label = get_period_label(period)
    lines = [f"<b>\U0001f4ca \u0410\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0430 {label}</b>\n"]

    # Общий средний балл
    current_avg = compute_overall_average(current_grades)
    previous_avg = compute_overall_average(previous_grades)

    if current_avg is None:
        lines.append("\U0001f4ed \u0417\u0430 \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u044b\u0439 \u043f\u0435\u0440\u0438\u043e\u0434 \u0447\u0438\u0441\u043b\u043e\u0432\u044b\u0445 \u043e\u0446\u0435\u043d\u043e\u043a \u043d\u0435\u0442")
        return "\n".join(lines)

    # Тренд общего балла
    avg_line = f"\U0001f4c8 <b>\u0421\u0440\u0435\u0434\u043d\u0438\u0439 \u0431\u0430\u043b\u043b: {current_avg:.2f}</b>"
    if previous_avg is not None:
        diff = current_avg - previous_avg
        if diff > _TREND_THRESHOLD:
            avg_line += f" {_TREND_ICONS['up']} (\u0431\u044b\u043b\u043e {previous_avg:.2f})"
        elif diff < -_TREND_THRESHOLD:
            avg_line += f" {_TREND_ICONS['down']} (\u0431\u044b\u043b\u043e {previous_avg:.2f})"
        else:
            avg_line += f" {_TREND_ICONS['stable']} (\u0431\u044b\u043b\u043e {previous_avg:.2f})"
    lines.append(avg_line)

    # По предметам
    current_avgs = compute_subject_averages(current_grades)
    previous_avgs = compute_subject_averages(previous_grades)
    trends = compute_trends(current_avgs, previous_avgs)

    if current_avgs:
        lines.append("\n<b>\u041f\u043e \u043f\u0440\u0435\u0434\u043c\u0435\u0442\u0430\u043c:</b>")

        # Сортировка по среднему (лучшие сверху)
        sorted_subjects = sorted(current_avgs.items(), key=lambda x: x[1], reverse=True)

        for subject, avg in sorted_subjects:
            safe_subj = html.escape(subject)
            trend_key = trends.get(subject, "stable")
            icon = _TREND_ICONS.get(trend_key, "")
            trend_label = _TREND_LABELS.get(trend_key, "")
            line = f"  {safe_subj} \u2014 <b>{avg:.2f}</b> {icon} {trend_label}"

            # Проверка длины сообщения
            current_len = len("\n".join(lines))
            if current_len + len(line) + 2 > _MAX_MESSAGE_LEN:
                remaining = len(sorted_subjects) - len([
                    l for l in lines if l.startswith("  ")
                ])
                lines.append(f"\n... \u0438 \u0435\u0449\u0451 {remaining} \u043f\u0440\u0435\u0434\u043c\u0435\u0442\u043e\u0432")
                break

            lines.append(line)

    # Распределение оценок
    dist = compute_grade_distribution(current_grades)
    if dist:
        total_numeric = sum(dist.values())
        lines.append(f"\n<b>\U0001f4cb \u0420\u0430\u0441\u043f\u0440\u0435\u0434\u0435\u043b\u0435\u043d\u0438\u0435 \u043e\u0446\u0435\u043d\u043e\u043a:</b>")

        for grade_val in sorted(dist.keys(), reverse=True):
            count = dist[grade_val]
            pct = round(count / total_numeric * 100)
            icon = _GRADE_ICONS.get(grade_val, "")
            lines.append(f"  {icon} {grade_val} \u2014 {count} \u0448\u0442. ({pct}%)")

    # Лучший и худший предметы
    if len(current_avgs) >= 2:
        sorted_subjs = sorted(current_avgs.items(), key=lambda x: x[1], reverse=True)
        best_subj, best_avg = sorted_subjs[0]
        worst_subj, worst_avg = sorted_subjs[-1]

        lines.append(f"\n\U0001f3c6 <b>\u041b\u0443\u0447\u0448\u0438\u0439:</b> {html.escape(best_subj)} ({best_avg:.2f})")
        lines.append(f"\U0001f4c9 <b>\u041f\u043e\u0434\u0442\u044f\u043d\u0443\u0442\u044c:</b> {html.escape(worst_subj)} ({worst_avg:.2f})")

    return "\n".join(lines)
