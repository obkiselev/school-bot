"""Тесты сервиса уведомлений."""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest


# ============================================================================
# ФОРМАТИРОВАНИЕ ОЦЕНОК
# ============================================================================

class TestFormatGradesNotification:
    """Тесты _format_grades_notification."""

    def _call(self, data):
        from services.notification_service import _format_grades_notification
        return _format_grades_notification(data)

    def test_single_child_single_grade(self):
        data = [("Иван Иванов", [
            {"subject": "Математика", "grade_value": "5", "lesson_type": None, "comment": None},
        ])]
        result = self._call(data)
        assert "Математика" in result
        assert "<b>5</b>" in result

    def test_single_child_multiple_grades(self):
        data = [("Иван", [
            {"subject": "Математика", "grade_value": "5", "lesson_type": None, "comment": None},
            {"subject": "Русский", "grade_value": "4", "lesson_type": None, "comment": None},
        ])]
        result = self._call(data)
        assert "Математика" in result
        assert "Русский" in result

    def test_multiple_children_show_names(self):
        data = [
            ("Иван", [{"subject": "Математика", "grade_value": "5", "lesson_type": None, "comment": None}]),
            ("Мария", [{"subject": "Русский", "grade_value": "4", "lesson_type": None, "comment": None}]),
        ]
        result = self._call(data)
        assert "<b>Иван</b>" in result
        assert "<b>Мария</b>" in result

    def test_grade_with_lesson_type(self):
        data = [("Иван", [
            {"subject": "Математика", "grade_value": "5", "lesson_type": "контрольная", "comment": None},
        ])]
        result = self._call(data)
        assert "(контрольная)" in result

    def test_html_escaping(self):
        data = [("Иван", [
            {"subject": "<script>alert(1)</script>", "grade_value": "5", "lesson_type": None, "comment": None},
        ])]
        result = self._call(data)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


# ============================================================================
# ФОРМАТИРОВАНИЕ ДЗ
# ============================================================================

class TestFormatHomeworkNotification:
    """Тесты _format_homework_notification."""

    def _call(self, data):
        from services.notification_service import _format_homework_notification
        return _format_homework_notification(data)

    def test_single_homework(self):
        data = [("Иван", [
            {"subject": "Математика", "assignment": "Стр. 42, упр. 1-5", "due_date": "2026-03-06"},
        ])]
        result = self._call(data)
        assert "Математика" in result
        assert "Стр. 42" in result

    def test_long_assignment_truncated(self):
        long_text = "А" * 250
        data = [("Иван", [
            {"subject": "Русский", "assignment": long_text, "due_date": "2026-03-06"},
        ])]
        result = self._call(data)
        assert "..." in result
        assert len(result) < len(long_text) + 100

    def test_none_assignment(self):
        data = [("Иван", [
            {"subject": "Математика", "assignment": None, "due_date": "2026-03-06"},
        ])]
        result = self._call(data)
        assert "—" in result

    def test_multiple_children_show_names(self):
        data = [
            ("Иван", [{"subject": "Математика", "assignment": "тест", "due_date": "2026-03-06"}]),
            ("Мария", [{"subject": "Русский", "assignment": "тест", "due_date": "2026-03-06"}]),
        ]
        result = self._call(data)
        assert "<b>Иван</b>" in result
        assert "<b>Мария</b>" in result


# ============================================================================
# _safe_send_message
# ============================================================================

class TestSafeSendMessage:
    """Тесты отправки с retry и обработкой ошибок Telegram."""

    @pytest.fixture(autouse=True)
    def setup_patches(self):
        """Мокаем _bot и asyncio.sleep для всех тестов."""
        self.mock_bot = MagicMock()
        self.mock_bot.send_message = AsyncMock()
        with patch("services.notification_service._bot", self.mock_bot), \
             patch("services.notification_service.asyncio.sleep", new_callable=AsyncMock):
            yield

    async def test_success(self):
        from services.notification_service import _safe_send_message
        result = await _safe_send_message(123, "test")
        assert result is True
        self.mock_bot.send_message.assert_called_once()

    async def test_forbidden_disables_notifications(self):
        from services.notification_service import _safe_send_message
        self.mock_bot.send_message.side_effect = TelegramForbiddenError(
            method=MagicMock(), message="Forbidden"
        )
        with patch("services.notification_service.disable_all_notifications", new_callable=AsyncMock) as mock_disable:
            result = await _safe_send_message(123, "test")
            assert result is False
            mock_disable.assert_called_once_with(123)

    async def test_bad_request_no_retry(self):
        from services.notification_service import _safe_send_message
        self.mock_bot.send_message.side_effect = TelegramBadRequest(
            method=MagicMock(), message="Bad Request"
        )
        result = await _safe_send_message(123, "test")
        assert result is False
        assert self.mock_bot.send_message.call_count == 1

    async def test_retry_on_generic_error_then_success(self):
        from services.notification_service import _safe_send_message
        self.mock_bot.send_message.side_effect = [
            Exception("network error"),
            Exception("timeout"),
            None,  # success on 3rd attempt
        ]
        result = await _safe_send_message(123, "test")
        assert result is True
        assert self.mock_bot.send_message.call_count == 3

    async def test_all_retries_exhausted(self):
        from services.notification_service import _safe_send_message
        self.mock_bot.send_message.side_effect = Exception("fail")
        result = await _safe_send_message(123, "test")
        assert result is False
        assert self.mock_bot.send_message.call_count == 3

    async def test_bot_not_initialized(self):
        with patch("services.notification_service._bot", None):
            from services.notification_service import _safe_send_message
            result = await _safe_send_message(123, "test")
            assert result is False


# ============================================================================
# check_and_send_missed
# ============================================================================

class TestCheckAndSendMissed:
    """Тесты досылки пропущенных уведомлений при старте."""

    def _make_now(self, hour, minute=0):
        """Создать datetime с нужным временем в московском TZ."""
        import pytz
        tz = pytz.timezone("Europe/Moscow")
        return datetime(2026, 3, 5, hour, minute, 0, tzinfo=tz)

    @pytest.fixture(autouse=True)
    def setup_settings(self):
        """Мокаем settings с фиксированными значениями."""
        with patch("services.notification_service.settings") as mock_settings:
            mock_settings.TIMEZONE = "Europe/Moscow"
            mock_settings.GRADES_NOTIFICATION_TIME = "18:00"
            mock_settings.HOMEWORK_NOTIFICATION_TIME = "19:00"
            self.mock_settings = mock_settings
            yield

    @patch("services.notification_service._send_homework_notifications", new_callable=AsyncMock)
    @patch("services.notification_service._send_grades_notifications", new_callable=AsyncMock)
    @patch("services.notification_service.get_last_notification_run", new_callable=AsyncMock)
    async def test_grades_missed_and_sent(self, mock_last_run, mock_send_grades, mock_send_hw):
        mock_last_run.return_value = "2026-03-04"  # yesterday
        with patch("services.notification_service.datetime") as mock_dt:
            mock_dt.now.return_value = self._make_now(20, 0)  # 20:00
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            from services.notification_service import check_and_send_missed
            await check_and_send_missed(MagicMock())
        mock_send_grades.assert_called_once()
        mock_send_hw.assert_called_once()

    @patch("services.notification_service._send_homework_notifications", new_callable=AsyncMock)
    @patch("services.notification_service._send_grades_notifications", new_callable=AsyncMock)
    @patch("services.notification_service.get_last_notification_run", new_callable=AsyncMock)
    async def test_already_ran_today_skipped(self, mock_last_run, mock_send_grades, mock_send_hw):
        mock_last_run.return_value = "2026-03-05"  # today
        with patch("services.notification_service.datetime") as mock_dt:
            mock_dt.now.return_value = self._make_now(20, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            from services.notification_service import check_and_send_missed
            await check_and_send_missed(MagicMock())
        mock_send_grades.assert_not_called()
        mock_send_hw.assert_not_called()

    @patch("services.notification_service._send_homework_notifications", new_callable=AsyncMock)
    @patch("services.notification_service._send_grades_notifications", new_callable=AsyncMock)
    @patch("services.notification_service.get_last_notification_run", new_callable=AsyncMock)
    async def test_before_scheduled_time_skipped(self, mock_last_run, mock_send_grades, mock_send_hw):
        mock_last_run.return_value = "2026-03-04"  # yesterday
        with patch("services.notification_service.datetime") as mock_dt:
            mock_dt.now.return_value = self._make_now(15, 0)  # 15:00, before 18:00
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            from services.notification_service import check_and_send_missed
            await check_and_send_missed(MagicMock())
        mock_send_grades.assert_not_called()
        mock_send_hw.assert_not_called()

    @patch("services.notification_service._send_homework_notifications", new_callable=AsyncMock)
    @patch("services.notification_service._send_grades_notifications", new_callable=AsyncMock)
    @patch("services.notification_service.get_last_notification_run", new_callable=AsyncMock)
    async def test_never_run_before(self, mock_last_run, mock_send_grades, mock_send_hw):
        mock_last_run.return_value = None  # never
        with patch("services.notification_service.datetime") as mock_dt:
            mock_dt.now.return_value = self._make_now(20, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            from services.notification_service import check_and_send_missed
            await check_and_send_missed(MagicMock())
        mock_send_grades.assert_called_once()
        mock_send_hw.assert_called_once()

    @patch("services.notification_service._send_homework_notifications", new_callable=AsyncMock)
    @patch("services.notification_service._send_grades_notifications", new_callable=AsyncMock)
    @patch("services.notification_service.get_last_notification_run", new_callable=AsyncMock)
    async def test_between_grades_and_homework_time(self, mock_last_run, mock_send_grades, mock_send_hw):
        """18:30 — оценки пропущены (>18:00), ДЗ ещё нет (<19:00)."""
        mock_last_run.return_value = "2026-03-04"
        with patch("services.notification_service.datetime") as mock_dt:
            mock_dt.now.return_value = self._make_now(18, 30)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            from services.notification_service import check_and_send_missed
            await check_and_send_missed(MagicMock())
        mock_send_grades.assert_called_once()
        mock_send_hw.assert_not_called()


# ============================================================================
# CRUD notification_runs
# ============================================================================

class TestNotificationRunCRUD:
    """Тесты save/get_last_notification_run."""

    @patch("database.crud.get_db")
    async def test_save_notification_run(self, mock_get_db):
        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_get_db.return_value = mock_db

        from database.crud import save_notification_run
        await save_notification_run("grades", "2026-03-05")
        mock_db.execute.assert_called_once()
        args = mock_db.execute.call_args
        assert "INSERT OR REPLACE" in args[0][0]
        assert ("grades", "2026-03-05") == args[0][1]

    @patch("database.crud.get_db")
    async def test_get_last_run_exists(self, mock_get_db):
        mock_db = MagicMock()
        mock_db.fetchone = AsyncMock(return_value=("2026-03-05",))
        mock_get_db.return_value = mock_db

        from database.crud import get_last_notification_run
        result = await get_last_notification_run("grades")
        assert result == "2026-03-05"

    @patch("database.crud.get_db")
    async def test_get_last_run_none(self, mock_get_db):
        mock_db = MagicMock()
        mock_db.fetchone = AsyncMock(return_value=None)
        mock_get_db.return_value = mock_db

        from database.crud import get_last_notification_run
        result = await get_last_notification_run("homework")
        assert result is None


# ============================================================================
# mark_notified ТОЛЬКО при успехе отправки
# ============================================================================

class TestMarkOnlyOnSuccess:
    """Проверяем, что mark_*_notified НЕ вызывается при ошибке отправки."""

    @patch("services.notification_service.log_activity", new_callable=AsyncMock)
    @patch("services.notification_service.mark_grades_notified", new_callable=AsyncMock)
    @patch("services.notification_service._safe_send_message", new_callable=AsyncMock)
    @patch("services.notification_service.get_unnotified_grades", new_callable=AsyncMock)
    @patch("services.notification_service.cache_new_grades", new_callable=AsyncMock)
    @patch("services.notification_service.MeshClient")
    @patch("services.notification_service.get_user_children", new_callable=AsyncMock)
    @patch("services.notification_service.get_user", new_callable=AsyncMock)
    @patch("services.notification_service.ensure_token", new_callable=AsyncMock)
    async def test_grades_not_marked_on_failure(
        self, mock_token, mock_get_user, mock_get_children,
        MockClient, mock_cache, mock_unnotified, mock_send,
        mock_mark, mock_log,
    ):
        mock_token.return_value = "token"
        mock_get_user.return_value = {"mesh_profile_id": 1}
        mock_get_children.return_value = [
            {"child_id": 1, "student_id": 100, "first_name": "Иван", "last_name": "Иванов"}
        ]

        mock_client = MagicMock()
        mock_client.get_grades = AsyncMock(return_value=[
            MagicMock(subject="Математика", grade_value="5", date="2026-03-05",
                      lesson_type=None, teacher=None, comment=None)
        ])
        mock_client.close = AsyncMock()
        MockClient.return_value = mock_client

        mock_cache.return_value = 1
        mock_unnotified.return_value = [
            {"grade_id": 1, "subject": "Математика", "grade_value": "5",
             "date": "2026-03-05", "lesson_type": None, "comment": None}
        ]
        mock_send.return_value = False  # send failed!

        from services.notification_service import _process_grades_for_user
        await _process_grades_for_user(12345, [{"user_id": 12345}])

        mock_mark.assert_not_called()
        mock_log.assert_not_called()

    @patch("services.notification_service.log_activity", new_callable=AsyncMock)
    @patch("services.notification_service.mark_grades_notified", new_callable=AsyncMock)
    @patch("services.notification_service._safe_send_message", new_callable=AsyncMock)
    @patch("services.notification_service.get_unnotified_grades", new_callable=AsyncMock)
    @patch("services.notification_service.cache_new_grades", new_callable=AsyncMock)
    @patch("services.notification_service.MeshClient")
    @patch("services.notification_service.get_user_children", new_callable=AsyncMock)
    @patch("services.notification_service.get_user", new_callable=AsyncMock)
    @patch("services.notification_service.ensure_token", new_callable=AsyncMock)
    async def test_grades_marked_on_success(
        self, mock_token, mock_get_user, mock_get_children,
        MockClient, mock_cache, mock_unnotified, mock_send,
        mock_mark, mock_log,
    ):
        mock_token.return_value = "token"
        mock_get_user.return_value = {"mesh_profile_id": 1}
        mock_get_children.return_value = [
            {"child_id": 1, "student_id": 100, "first_name": "Иван", "last_name": "Иванов"}
        ]

        mock_client = MagicMock()
        mock_client.get_grades = AsyncMock(return_value=[
            MagicMock(subject="Математика", grade_value="5", date="2026-03-05",
                      lesson_type=None, teacher=None, comment=None)
        ])
        mock_client.close = AsyncMock()
        MockClient.return_value = mock_client

        mock_cache.return_value = 1
        mock_unnotified.return_value = [
            {"grade_id": 1, "subject": "Математика", "grade_value": "5",
             "date": "2026-03-05", "lesson_type": None, "comment": None}
        ]
        mock_send.return_value = True  # send ok!

        from services.notification_service import _process_grades_for_user
        await _process_grades_for_user(12345, [{"user_id": 12345}])

        mock_mark.assert_called_once()
        mock_log.assert_called_once()


class TestHomeworkSummaryBehavior:
    @patch("services.notification_service.was_homework_summary_sent", new_callable=AsyncMock)
    @patch("services.notification_service.get_user_children", new_callable=AsyncMock)
    @patch("services.notification_service.get_user", new_callable=AsyncMock)
    @patch("services.notification_service.ensure_token", new_callable=AsyncMock)
    async def test_homework_summary_skips_already_sent(
        self, mock_token, mock_get_user, mock_get_children, mock_sent
    ):
        mock_token.return_value = "token"
        mock_get_user.return_value = {"mesh_profile_id": 1}
        mock_get_children.return_value = [
            {"child_id": 1, "student_id": 100, "first_name": "Иван", "last_name": "Иванов"}
        ]
        mock_sent.return_value = True

        with patch(
            "services.notification_service._is_student_homework_window_open",
            new=AsyncMock(return_value=(True, 1, 0)),
        ), patch(
            "services.notification_service._safe_send_message",
            new=AsyncMock(),
        ) as mock_send:
            from services.notification_service import _process_homework_for_user
            result = await _process_homework_for_user(12345, [{"user_id": 12345}])

        assert result.status == "no_changes"
        mock_send.assert_not_called()

    def test_single_child_name_always_present_in_homework_format(self):
        from services.notification_service import _format_homework_notification

        result = _format_homework_notification(
            [("Иван Иванов", [{"subject": "Математика", "assignment": "стр. 42", "due_date": "2026-03-11"}])],
            "2026-03-11",
        )

        assert "<b>Иван Иванов</b>" in result
        assert "11.03.2026" in result

    def test_single_child_name_and_date_present_in_grades_format(self):
        from services.notification_service import _format_grades_notification

        result = _format_grades_notification(
            [("Иван Иванов", [{"subject": "Математика", "grade_value": "5", "lesson_type": None}])],
            "2026-03-10",
        )

        assert "<b>Иван Иванов</b>" in result
        assert "10.03.2026" in result


class TestHomeworkUpdates:
    def test_classify_homework_changes(self):
        from services.notification_service import _classify_homework_changes

        known = [
            {"subject": "Математика", "assignment": "стр. 10"},
            {"subject": "Русский", "assignment": "упр. 1"},
        ]
        new = [
            {"subject": "Физика", "assignment": "§5"},
            {"subject": "Русский", "assignment": "упр. 2"},
        ]

        added, changed = _classify_homework_changes(new, known)
        assert len(added) == 1
        assert added[0]["subject"] == "Физика"
        assert len(changed) == 1
        assert changed[0]["subject"] == "Русский"

    @patch("services.notification_service.log_activity", new_callable=AsyncMock)
    @patch("services.notification_service.mark_homework_notified", new_callable=AsyncMock)
    @patch("services.notification_service._safe_send_message", new_callable=AsyncMock)
    @patch("services.notification_service.get_unnotified_homework_for_date", new_callable=AsyncMock)
    @patch("services.notification_service.get_notified_homework_for_date", new_callable=AsyncMock)
    @patch("services.notification_service.cache_new_homework", new_callable=AsyncMock)
    @patch("services.notification_service.MeshClient")
    @patch("services.notification_service.was_homework_summary_sent", new_callable=AsyncMock)
    @patch("services.notification_service.get_user_children", new_callable=AsyncMock)
    @patch("services.notification_service.get_user", new_callable=AsyncMock)
    @patch("services.notification_service.ensure_token", new_callable=AsyncMock)
    async def test_updates_sent_on_new_or_changed_homework(
        self,
        mock_token,
        mock_get_user,
        mock_get_children,
        mock_summary_sent,
        MockClient,
        mock_cache_new,
        mock_known,
        mock_unnotified,
        mock_send,
        mock_mark,
        mock_log,
    ):
        mock_token.return_value = "token"
        mock_get_user.return_value = {"mesh_profile_id": 1}
        mock_get_children.return_value = [
            {"child_id": 1, "student_id": 100, "first_name": "Иван", "last_name": "Иванов"}
        ]
        mock_summary_sent.return_value = True

        mock_client = MagicMock()
        mock_client.get_homework = AsyncMock(return_value=[
            MagicMock(subject="Русский", assignment="упр. 2", due_date="2026-03-11")
        ])
        mock_client.close = AsyncMock()
        MockClient.return_value = mock_client

        mock_cache_new.return_value = 1
        mock_known.return_value = [{"subject": "Русский", "assignment": "упр. 1", "due_date": "2026-03-11"}]
        mock_unnotified.return_value = [
            {"homework_id": 101, "subject": "Русский", "assignment": "упр. 2", "due_date": "2026-03-11"}
        ]
        mock_send.return_value = True

        from services.notification_service import _process_homework_updates_for_user
        result = await _process_homework_updates_for_user(12345, [{"user_id": 12345}])

        assert result.status == "sent"
        mock_send.assert_called_once()
        mock_mark.assert_called_once_with([101])
        mock_log.assert_called_once()
