"""Тесты для обработчика /raspisanie и вспомогательных функций."""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from mesh_api.models import Lesson
from mesh_api.exceptions import AuthenticationError, MeshAPIError
from handlers.schedule import (
    _format_day_schedule,
    _format_week_schedule,
    _parse_callback_data,
    _get_week_dates,
    cmd_raspisanie,
    _handle_schedule_request,
)
from utils.token_manager import _is_token_valid, ensure_token


# ============================================================================
# ТЕСТЫ ФОРМАТИРОВАНИЯ (чистые функции, без моков)
# ============================================================================


class TestFormatDaySchedule:
    """Тесты форматирования расписания на один день."""

    def test_format_day_schedule_full(self, today, sample_lessons):
        """Полный список уроков со всеми полями — корректный форматированный текст."""
        result = _format_day_schedule(today, sample_lessons)

        assert "25 февраля (среда)" in result
        assert "Математика" in result
        assert "Русский язык" in result
        assert "08:30" in result
        assert "09:15" in result
        assert "Иванова А.П." in result
        assert "Каб. 301" in result
        assert "Петрова М.И." in result
        assert "Каб. 205" in result

    def test_format_day_schedule_missing_teacher(self, today):
        """Урок без учителя — кабинет показан, строка учителя пропущена."""
        lessons = [
            Lesson(
                number=1,
                subject="Физика",
                time_start="08:30",
                time_end="09:15",
                teacher=None,
                room="101",
            )
        ]
        result = _format_day_schedule(today, lessons)

        assert "Каб. 101" in result
        assert "\U0001f468\u200d\U0001f3eb" not in result

    def test_format_day_schedule_missing_room(self, today):
        """Урок без кабинета — учитель показан, кабинет пропущен."""
        lessons = [
            Lesson(
                number=1,
                subject="Физика",
                time_start="08:30",
                time_end="09:15",
                teacher="Сидоров В.Г.",
                room=None,
            )
        ]
        result = _format_day_schedule(today, lessons)

        assert "Сидоров В.Г." in result
        assert "Каб." not in result

    def test_format_day_schedule_empty(self, today):
        """Пустой список уроков — сообщение 'На этот день уроков нет'."""
        result = _format_day_schedule(today, [])

        assert "На этот день уроков нет" in result

    def test_format_day_html_escape(self, today):
        """HTML-символы в названии предмета экранируются."""
        lessons = [
            Lesson(
                number=1,
                subject="Физика <углублённая>",
                time_start="08:30",
                time_end="09:15",
                teacher="Учитель & помощник",
                room="<301>",
            )
        ]
        result = _format_day_schedule(today, lessons)

        assert "&lt;углублённая&gt;" in result
        assert "&amp; помощник" in result
        assert "&lt;301&gt;" in result
        assert "<углублённая>" not in result


class TestFormatWeekSchedule:
    """Тесты форматирования расписания на неделю."""

    def test_format_week_schedule(self, sample_lessons):
        """Несколько дней — объединены с заголовками дней."""
        monday = date(2026, 2, 23)
        tuesday = date(2026, 2, 24)
        results = [
            (monday, sample_lessons),
            (tuesday, [Lesson(number=1, subject="Физика",
                              time_start="08:30", time_end="09:15",
                              teacher="Сидоров В.Г.", room="101")]),
        ]
        result = _format_week_schedule(results)

        assert result is not None
        assert "23 февраля (понедельник)" in result
        assert "24 февраля (вторник)" in result
        assert "Математика" in result
        assert "Физика" in result

    def test_format_week_partial_failure(self, sample_lessons):
        """Часть дней None — показаны только успешные + пометка ошибки."""
        monday = date(2026, 2, 23)
        tuesday = date(2026, 2, 24)
        results = [
            (monday, sample_lessons),
            (tuesday, None),
        ]
        result = _format_week_schedule(results)

        assert result is not None
        assert "23 февраля (понедельник)" in result
        assert "Математика" in result
        assert "Не удалось загрузить" in result

    def test_format_week_all_failed(self):
        """Все дни None — возвращает None."""
        monday = date(2026, 2, 23)
        tuesday = date(2026, 2, 24)
        results = [
            (monday, None),
            (tuesday, None),
        ]
        result = _format_week_schedule(results)

        assert result is None


# ============================================================================
# ТЕСТЫ ПАРСИНГА CALLBACK DATA
# ============================================================================


class TestParseCallbackData:
    """Тесты парсинга callback_data."""

    def test_parse_callback_valid(self):
        """Валидный callback 'sched:period:123:today' — корректный кортеж."""
        result = _parse_callback_data("sched:period:123:today")
        assert result == ("period", 123, "today")

    def test_parse_callback_no_extra(self):
        """Callback без extra 'sched:child:123' — extra=None."""
        result = _parse_callback_data("sched:child:123")
        assert result == ("child", 123, None)

    def test_parse_callback_malformed(self):
        """Невалидный callback 'invalid' — None."""
        result = _parse_callback_data("invalid")
        assert result is None

    def test_parse_callback_bad_student_id(self):
        """Нечисловой student_id 'sched:child:abc' — None."""
        result = _parse_callback_data("sched:child:abc")
        assert result is None


# ============================================================================
# ТЕСТЫ РАСЧЁТА ДАТ НЕДЕЛИ
# ============================================================================


class TestGetWeekDates:
    """Тесты получения дат Пн-Пт текущей недели."""

    def test_get_week_dates_monday(self):
        """Из понедельника — Пн-Пт той же недели."""
        monday = date(2026, 2, 23)
        result = _get_week_dates(monday)

        assert len(result) == 5
        assert result[0] == date(2026, 2, 23)
        assert result[4] == date(2026, 2, 27)

    def test_get_week_dates_wednesday(self):
        """Из среды — Пн-Пт той же недели."""
        wednesday = date(2026, 2, 25)
        result = _get_week_dates(wednesday)

        assert len(result) == 5
        assert result[0] == date(2026, 2, 23)
        assert result[4] == date(2026, 2, 27)

    def test_get_week_dates_sunday(self):
        """Из воскресенья — Пн-Пт той же недели."""
        sunday = date(2026, 3, 1)
        result = _get_week_dates(sunday)

        assert len(result) == 5
        assert result[0] == date(2026, 2, 23)
        assert result[4] == date(2026, 2, 27)


# ============================================================================
# ТЕСТЫ TOKEN MANAGER (мок БД и API)
# ============================================================================


def _make_user_dict(token: str = "old_token", expires_at: str = None) -> dict:
    """Создаёт словарь пользователя для моков ensure_token."""
    return {
        "user_id": 12345,
        "mesh_login": "login",
        "mesh_password": "pass",
        "mesh_token": token,
        "token_expires_at": expires_at,
    }


class TestTokenManager:
    """Тесты менеджера токенов (ensure_token + _is_token_valid)."""

    @patch("utils.token_manager.update_user_token", new_callable=AsyncMock)
    @patch("utils.token_manager.MeshClient")
    @patch("utils.token_manager.get_user", new_callable=AsyncMock)
    async def test_token_valid_no_refresh(
        self, mock_get_user, mock_mesh_client_cls, mock_update_token
    ):
        """Токен ещё действителен — возвращается без вызова API."""
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        mock_get_user.return_value = _make_user_dict("existing_token", future_time)

        result = await ensure_token(12345)

        assert result == "existing_token"
        mock_mesh_client_cls.assert_not_called()
        mock_update_token.assert_not_called()

    @patch("utils.token_manager.update_user_token", new_callable=AsyncMock)
    @patch("utils.token_manager.MeshClient")
    @patch("utils.token_manager.get_user", new_callable=AsyncMock)
    async def test_token_expired_refresh(
        self, mock_get_user, mock_mesh_client_cls, mock_update_token
    ):
        """Токен истёк — вызывается authenticate, новый токен сохраняется."""
        past_time = (datetime.now() - timedelta(hours=1)).isoformat()
        mock_get_user.return_value = _make_user_dict("old_token", past_time)

        mock_client = AsyncMock()
        mock_client.authenticate.return_value = {
            "token": "new_token",
            "expires_at": "2026-03-01T15:00:00",
        }
        mock_mesh_client_cls.return_value = mock_client

        result = await ensure_token(12345)

        assert result == "new_token"
        mock_client.authenticate.assert_awaited_once_with("login", "pass")
        mock_update_token.assert_awaited_once_with(
            12345, "new_token", "2026-03-01T15:00:00"
        )
        mock_client.close.assert_awaited_once()

    @patch("utils.token_manager.update_user_token", new_callable=AsyncMock)
    @patch("utils.token_manager.MeshClient")
    @patch("utils.token_manager.get_user", new_callable=AsyncMock)
    async def test_token_none_refresh(
        self, mock_get_user, mock_mesh_client_cls, mock_update_token
    ):
        """token_expires_at=None — обновление запускается."""
        mock_get_user.return_value = _make_user_dict("old_token", None)

        mock_client = AsyncMock()
        mock_client.authenticate.return_value = {
            "token": "refreshed_token",
            "expires_at": "2026-03-01T15:00:00",
        }
        mock_mesh_client_cls.return_value = mock_client

        result = await ensure_token(12345)

        assert result == "refreshed_token"
        mock_client.authenticate.assert_awaited_once()

    @patch("utils.token_manager.MeshClient")
    @patch("utils.token_manager.get_user", new_callable=AsyncMock)
    async def test_token_refresh_failure(
        self, mock_get_user, mock_mesh_client_cls
    ):
        """authenticate бросает AuthenticationError — пробрасывается наверх."""
        past_time = (datetime.now() - timedelta(hours=1)).isoformat()
        mock_get_user.return_value = _make_user_dict("old_token", past_time)

        mock_client = AsyncMock()
        mock_client.authenticate.side_effect = AuthenticationError("Auth failed")
        mock_mesh_client_cls.return_value = mock_client

        with pytest.raises(AuthenticationError):
            await ensure_token(12345)

        mock_client.close.assert_awaited_once()

    @patch("utils.token_manager.get_user", new_callable=AsyncMock)
    async def test_token_user_not_found(self, mock_get_user):
        """Пользователь не найден в БД — AuthenticationError."""
        mock_get_user.return_value = None

        with pytest.raises(AuthenticationError, match="не зарегистрирован"):
            await ensure_token(99999)

    @patch("utils.token_manager.datetime")
    def test_token_buffer_edge(self, mock_datetime):
        """Токен истекает через 4 минуты (в пределах 5-мин буфера) — невалиден."""
        fixed_now = datetime(2026, 2, 25, 12, 0, 0)
        mock_datetime.now.return_value = fixed_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        expires_at = "2026-02-25T12:04:00"
        assert _is_token_valid(expires_at) is False

    @patch("utils.token_manager.datetime")
    def test_token_valid_outside_buffer(self, mock_datetime):
        """Токен истекает через 10 минут (за пределами буфера) — валиден."""
        fixed_now = datetime(2026, 2, 25, 12, 0, 0)
        mock_datetime.now.return_value = fixed_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        expires_at = "2026-02-25T12:10:00"
        assert _is_token_valid(expires_at) is True

    @patch("utils.token_manager.datetime")
    def test_token_exact_buffer_boundary(self, mock_datetime):
        """Токен истекает ровно через 5 минут (граница буфера) — невалиден (strict >)."""
        fixed_now = datetime(2026, 2, 25, 12, 0, 0)
        mock_datetime.now.return_value = fixed_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        expires_at = "2026-02-25T12:05:00"
        assert _is_token_valid(expires_at) is False


# ============================================================================
# ТЕСТЫ ОБРАБОТЧИКОВ (мок БД + API + ensure_token)
# ============================================================================


def _make_mock_message(user_id: int = 12345) -> AsyncMock:
    """Создаёт мок объекта Message."""
    message = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.answer = AsyncMock()
    return message


def _make_mock_callback(
    user_id: int = 12345, data: str = "sched:child:100"
) -> AsyncMock:
    """Создаёт мок объекта CallbackQuery."""
    callback = AsyncMock()
    callback.from_user = MagicMock()
    callback.from_user.id = user_id
    callback.data = data
    callback.message = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    return callback


class TestCmdRaspisanie:
    """Тесты обработчика команды /raspisanie."""

    @patch("handlers.schedule.get_user", new_callable=AsyncMock)
    async def test_cmd_unregistered_user(self, mock_get_user):
        """Незарегистрированный пользователь — сообщение 'Сначала зарегистрируйтесь'."""
        mock_get_user.return_value = None
        message = _make_mock_message()

        await cmd_raspisanie(message)

        mock_get_user.assert_awaited_once_with(12345)
        message.answer.assert_awaited_once()
        call_text = message.answer.call_args[0][0]
        assert "зарегистрируйтесь" in call_text.lower()

    @patch("handlers.schedule.get_user_children", new_callable=AsyncMock)
    @patch("handlers.schedule.get_user", new_callable=AsyncMock)
    async def test_cmd_no_children(self, mock_get_user, mock_get_children, sample_user):
        """Зарегистрированный пользователь без детей — сообщение 'нет привязанных детей'."""
        mock_get_user.return_value = sample_user
        mock_get_children.return_value = []

        message = _make_mock_message()

        await cmd_raspisanie(message)

        message.answer.assert_awaited_once()
        call_text = message.answer.call_args[0][0]
        assert "нет привязанных детей" in call_text.lower()

    @patch("handlers.schedule.MeshClient")
    @patch("handlers.schedule.ensure_token", new_callable=AsyncMock)
    @patch("handlers.schedule.get_user_children", new_callable=AsyncMock)
    @patch("handlers.schedule.get_user", new_callable=AsyncMock)
    async def test_cmd_single_child(
        self,
        mock_get_user,
        mock_get_children,
        mock_ensure_token,
        mock_mesh_client_cls,
        sample_user,
        sample_children,
        sample_lessons,
    ):
        """Один ребёнок — расписание показывается сразу с содержимым."""
        mock_get_user.return_value = sample_user
        mock_get_children.return_value = sample_children
        mock_ensure_token.return_value = "valid_token"

        mock_client = AsyncMock()
        mock_client.get_schedule.return_value = sample_lessons
        mock_mesh_client_cls.return_value = mock_client

        message = _make_mock_message()

        await cmd_raspisanie(message)

        message.answer.assert_awaited_once()
        call_kwargs = message.answer.call_args
        assert call_kwargs.kwargs.get("parse_mode") == "HTML"
        assert call_kwargs.kwargs.get("reply_markup") is not None
        call_text = call_kwargs[0][0]
        assert "Математика" in call_text

    @patch("handlers.schedule.get_user_children", new_callable=AsyncMock)
    @patch("handlers.schedule.get_user", new_callable=AsyncMock)
    async def test_cmd_multiple_children(
        self,
        mock_get_user,
        mock_get_children,
        sample_user,
        multiple_children,
    ):
        """Несколько детей — показывается клавиатура выбора ребёнка."""
        mock_get_user.return_value = sample_user
        mock_get_children.return_value = multiple_children

        message = _make_mock_message()

        await cmd_raspisanie(message)

        message.answer.assert_awaited_once()
        call_text = message.answer.call_args[0][0]
        assert "Выберите ребёнка" in call_text
        call_kwargs = message.answer.call_args
        keyboard = call_kwargs.kwargs.get("reply_markup")
        assert keyboard is not None

    @patch("handlers.schedule.MeshClient")
    @patch("handlers.schedule.ensure_token", new_callable=AsyncMock)
    @patch("handlers.schedule.get_user_children", new_callable=AsyncMock)
    @patch("handlers.schedule.get_user", new_callable=AsyncMock)
    async def test_cmd_api_error(
        self,
        mock_get_user,
        mock_get_children,
        mock_ensure_token,
        mock_mesh_client_cls,
        sample_user,
        sample_children,
    ):
        """MeshAPIError — сообщение 'Сервис МЭШ временно недоступен' + кнопка повтора."""
        mock_get_user.return_value = sample_user
        mock_get_children.return_value = sample_children
        mock_ensure_token.return_value = "valid_token"

        mock_client = AsyncMock()
        mock_client.get_schedule.side_effect = MeshAPIError("API down")
        mock_mesh_client_cls.return_value = mock_client

        message = _make_mock_message()

        await cmd_raspisanie(message)

        message.answer.assert_awaited()
        call_text = message.answer.call_args[0][0]
        assert "временно недоступен" in call_text

    @patch("handlers.schedule.ensure_token", new_callable=AsyncMock)
    @patch("handlers.schedule.get_user_children", new_callable=AsyncMock)
    @patch("handlers.schedule.get_user", new_callable=AsyncMock)
    async def test_cmd_auth_error(
        self,
        mock_get_user,
        mock_get_children,
        mock_ensure_token,
        sample_user,
        sample_children,
    ):
        """AuthenticationError от ensure_token — сообщение 'Перерегистрируйтесь'."""
        mock_get_user.return_value = sample_user
        mock_get_children.return_value = sample_children
        mock_ensure_token.side_effect = AuthenticationError("Auth failed")

        message = _make_mock_message()

        await cmd_raspisanie(message)

        message.answer.assert_awaited_once()
        call_text = message.answer.call_args[0][0]
        assert "перерегистрируйтесь" in call_text.lower()


# ============================================================================
# ТЕСТ IDOR-ЗАЩИТЫ
# ============================================================================


class TestIDORProtection:
    """Тест защиты от IDOR — подмены student_id в callback_data."""

    @patch("handlers.schedule.ensure_token", new_callable=AsyncMock)
    @patch("handlers.schedule.get_user_children", new_callable=AsyncMock)
    async def test_ownership_check(
        self, mock_get_children, mock_ensure_token, sample_children
    ):
        """Callback с чужим student_id — молча игнорируется, ensure_token не вызывается."""
        mock_get_children.return_value = sample_children

        callback = _make_mock_callback(user_id=12345)

        await _handle_schedule_request(callback, student_id=999, period="today")

        callback.message.edit_text.assert_not_awaited()
        mock_ensure_token.assert_not_awaited()
