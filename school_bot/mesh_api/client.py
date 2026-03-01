"""Main МЭШ API client — обёртка над OctoDiary."""
import logging
from typing import List, Optional
from datetime import date, timedelta

from octodiary.apis.async_ import AsyncMobileAPI
from octodiary.urls import Systems

from .exceptions import (
    AuthenticationError, NetworkError, InvalidResponseError, MeshAPIError
)
from .models import (
    Student, Lesson, Grade, Homework,
    student_from_octodiary, lesson_from_event,
    grade_from_payload, homework_from_payload,
)

logger = logging.getLogger(__name__)


class MeshClient:
    """Async client for МЭШ API via OctoDiary."""

    def __init__(self, token: Optional[str] = None, profile_id: Optional[int] = None):
        """
        Args:
            token: МЭШ access token (mesh_access_token)
            profile_id: ID профиля родителя (из get_users_profile_info)
        """
        self.api = AsyncMobileAPI(system=Systems.MES)
        if token:
            self.api.token = token
        self.profile_id = profile_id

    async def get_schedule(
        self,
        student_id: int,
        date_str: str,
        token: str,
        person_id: Optional[str] = None,
        mes_role: str = "parent",
    ) -> List[Lesson]:
        """
        Получить расписание на день.

        Args:
            student_id: ID ученика (child.id)
            date_str: Дата в формате YYYY-MM-DD
            token: МЭШ access token
            person_id: contingent_guid ребёнка (для events API)
            mes_role: Роль в МЭШ (parent/student)

        Returns:
            Список уроков, отсортированный по времени
        """
        self.api.token = token

        if not person_id:
            logger.warning("person_id не указан для student_id=%d, расписание может быть неполным", student_id)
            return []

        try:
            target_date = date.fromisoformat(date_str)
            events_resp = await self.api.get_events(
                person_id=person_id,
                mes_role=mes_role,
                begin_date=target_date,
                end_date=target_date,
            )
        except Exception as e:
            error_msg = str(e).lower()
            if "401" in error_msg or "unauthorized" in error_msg:
                raise AuthenticationError("Токен истек или недействителен")
            logger.error("Ошибка получения расписания: %s", e)
            raise NetworkError(f"Ошибка получения расписания: {e}")

        if not events_resp or not events_resp.response:
            return []

        lessons = []
        for event in events_resp.response:
            lesson = lesson_from_event(event)
            if lesson:
                lessons.append(lesson)

        # Сортируем по времени и проставляем номера уроков
        lessons.sort(key=lambda l: l.time_start)
        for i, lesson in enumerate(lessons, 1):
            lesson.number = i

        return lessons

    async def get_grades(
        self,
        student_id: int,
        from_date: str,
        to_date: str,
        token: str,
        profile_id: Optional[int] = None,
    ) -> List[Grade]:
        """
        Получить оценки за период.

        Args:
            student_id: ID ученика
            from_date: Начало периода (YYYY-MM-DD)
            to_date: Конец периода (YYYY-MM-DD)
            token: МЭШ access token
            profile_id: ID профиля родителя

        Returns:
            Список оценок
        """
        self.api.token = token
        pid = profile_id or self.profile_id

        if not pid:
            raise InvalidResponseError("profile_id не указан")

        try:
            marks_resp = await self.api.get_marks(
                student_id=student_id,
                profile_id=pid,
                from_date=date.fromisoformat(from_date),
                to_date=date.fromisoformat(to_date),
            )
        except Exception as e:
            error_msg = str(e).lower()
            if "401" in error_msg or "unauthorized" in error_msg:
                raise AuthenticationError("Токен истек или недействителен")
            logger.error("Ошибка получения оценок: %s", e)
            raise NetworkError(f"Ошибка получения оценок: {e}")

        if not marks_resp or not marks_resp.payload:
            return []

        grades = []
        for payload in marks_resp.payload:
            grade = grade_from_payload(payload)
            if grade:
                grades.append(grade)

        return grades

    async def get_homework(
        self,
        student_id: int,
        from_date: str,
        to_date: str,
        token: str,
        profile_id: Optional[int] = None,
    ) -> List[Homework]:
        """
        Получить домашние задания за период.

        Args:
            student_id: ID ученика
            from_date: Начало периода (YYYY-MM-DD)
            to_date: Конец периода (YYYY-MM-DD)
            token: МЭШ access token
            profile_id: ID профиля родителя

        Returns:
            Список домашних заданий
        """
        self.api.token = token
        pid = profile_id or self.profile_id

        if not pid:
            raise InvalidResponseError("profile_id не указан")

        try:
            hw_resp = await self.api.get_homeworks_short(
                student_id=student_id,
                profile_id=pid,
                from_date=date.fromisoformat(from_date),
                to_date=date.fromisoformat(to_date),
            )
        except Exception as e:
            error_msg = str(e).lower()
            if "401" in error_msg or "unauthorized" in error_msg:
                raise AuthenticationError("Токен истек или недействителен")
            logger.error("Ошибка получения ДЗ: %s", e)
            raise NetworkError(f"Ошибка получения ДЗ: {e}")

        if not hw_resp or not hw_resp.payload:
            return []

        homework_list = []
        for payload in hw_resp.payload:
            hw = homework_from_payload(payload)
            if hw:
                homework_list.append(hw)

        return homework_list

    async def get_profile(self, token: str) -> List[Student]:
        """
        Получить профиль с детьми.

        Args:
            token: МЭШ access token

        Returns:
            Список Student (детей)
        """
        self.api.token = token

        try:
            profiles = await self.api.get_users_profile_info()
        except Exception as e:
            logger.error("Ошибка получения профиля: %s", e)
            raise NetworkError(f"Ошибка получения профиля: {e}")

        if not profiles:
            return []

        profile_id = profiles[0].id
        self.profile_id = profile_id

        try:
            family = await self.api.get_family_profile(profile_id=profile_id)
        except Exception as e:
            logger.error("Ошибка получения семейного профиля: %s", e)
            raise NetworkError(f"Ошибка получения семейного профиля: {e}")

        if not family.children:
            return []

        return [student_from_octodiary(child) for child in family.children]

    async def close(self):
        """Закрыть сессию (для совместимости с существующим кодом)."""
        pass
