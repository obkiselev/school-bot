"""Тесты middleware контроля доступа."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import Message, CallbackQuery


def _make_event(user_id, text=None, is_callback=False, callback_data=None):
    """Создать мок-событие Telegram."""
    if is_callback:
        event = MagicMock(spec=CallbackQuery)
        event.from_user = MagicMock()
        event.from_user.id = user_id
        event.data = callback_data
        event.message = MagicMock()
        event.message.answer = AsyncMock()
        event.answer = AsyncMock()
    else:
        event = MagicMock(spec=Message)
        event.from_user = MagicMock()
        event.from_user.id = user_id
        event.text = text
        event.answer = AsyncMock()
    return event


def _make_data(state=None):
    """Создать dict с FSM state."""
    data = {}
    if state is not None:
        mock_fsm = AsyncMock()
        mock_fsm.get_state = AsyncMock(return_value=state)
        data["state"] = mock_fsm
    else:
        mock_fsm = AsyncMock()
        mock_fsm.get_state = AsyncMock(return_value=None)
        data["state"] = mock_fsm
    return data


class TestAccessControlMiddleware:
    """Тесты AccessControlMiddleware."""

    def _get_middleware(self):
        from middlewares.access import AccessControlMiddleware
        return AccessControlMiddleware()

    @patch("middlewares.access.settings")
    async def test_admin_always_passes(self, mock_settings):
        mock_settings.ADMIN_ID = 999
        mw = self._get_middleware()
        event = _make_event(999, text="/something")
        handler = AsyncMock(return_value="ok")
        result = await mw(handler, event, _make_data())
        handler.assert_called_once()

    @patch("middlewares.access.is_user_allowed", new_callable=AsyncMock)
    @patch("middlewares.access.settings")
    async def test_public_command_start(self, mock_settings, mock_allowed):
        mock_settings.ADMIN_ID = 999
        mw = self._get_middleware()
        event = _make_event(123, text="/start")
        handler = AsyncMock(return_value="ok")
        result = await mw(handler, event, _make_data())
        handler.assert_called_once()
        mock_allowed.assert_not_called()

    @patch("middlewares.access.is_user_allowed", new_callable=AsyncMock)
    @patch("middlewares.access.settings")
    async def test_public_command_help(self, mock_settings, mock_allowed):
        mock_settings.ADMIN_ID = 999
        mw = self._get_middleware()
        event = _make_event(123, text="/help")
        handler = AsyncMock(return_value="ok")
        result = await mw(handler, event, _make_data())
        handler.assert_called_once()
        mock_allowed.assert_not_called()

    @patch("middlewares.access.is_user_allowed", new_callable=AsyncMock)
    @patch("middlewares.access.settings")
    async def test_public_command_with_bot_suffix(self, mock_settings, mock_allowed):
        mock_settings.ADMIN_ID = 999
        mw = self._get_middleware()
        event = _make_event(123, text="/start@mybot")
        handler = AsyncMock(return_value="ok")
        result = await mw(handler, event, _make_data())
        handler.assert_called_once()

    @patch("middlewares.access.is_user_allowed", new_callable=AsyncMock)
    @patch("middlewares.access.settings")
    async def test_allowed_user_passes(self, mock_settings, mock_allowed):
        mock_settings.ADMIN_ID = 999
        mock_allowed.return_value = (True, "parent")
        mw = self._get_middleware()
        event = _make_event(123, text="/grades")
        handler = AsyncMock(return_value="ok")
        result = await mw(handler, event, _make_data())
        handler.assert_called_once()

    @patch("middlewares.access.is_user_allowed", new_callable=AsyncMock)
    @patch("middlewares.access.settings")
    async def test_blocked_user_denied(self, mock_settings, mock_allowed):
        mock_settings.ADMIN_ID = 999
        mock_allowed.return_value = (False, "parent")
        mw = self._get_middleware()
        event = _make_event(123, text="/grades")
        handler = AsyncMock()
        result = await mw(handler, event, _make_data())
        handler.assert_not_called()
        event.answer.assert_called()

    @patch("middlewares.access.is_user_allowed", new_callable=AsyncMock)
    @patch("middlewares.access.settings")
    async def test_unknown_user_denied(self, mock_settings, mock_allowed):
        mock_settings.ADMIN_ID = 999
        mock_allowed.return_value = (False, None)
        mw = self._get_middleware()
        event = _make_event(123, text="/grades")
        handler = AsyncMock()
        result = await mw(handler, event, _make_data())
        handler.assert_not_called()

    @patch("middlewares.access.is_user_allowed", new_callable=AsyncMock)
    @patch("middlewares.access.settings")
    async def test_fsm_active_bypasses_acl(self, mock_settings, mock_allowed):
        mock_settings.ADMIN_ID = 999
        mw = self._get_middleware()
        event = _make_event(123, text="some text")
        handler = AsyncMock(return_value="ok")
        data = _make_data(state="Registration:waiting_login")
        result = await mw(handler, event, data)
        handler.assert_called_once()
        mock_allowed.assert_not_called()

    @patch("middlewares.access.is_user_allowed", new_callable=AsyncMock)
    @patch("middlewares.access.settings")
    async def test_public_callback_passes(self, mock_settings, mock_allowed):
        mock_settings.ADMIN_ID = 999
        mw = self._get_middleware()
        event = _make_event(123, is_callback=True, callback_data="select_child_1")
        handler = AsyncMock(return_value="ok")
        result = await mw(handler, event, _make_data())
        handler.assert_called_once()

    @patch("middlewares.access.is_user_allowed", new_callable=AsyncMock)
    @patch("middlewares.access.settings")
    async def test_db_error_denies(self, mock_settings, mock_allowed):
        mock_settings.ADMIN_ID = 999
        mock_allowed.side_effect = Exception("DB error")
        mw = self._get_middleware()
        event = _make_event(123, text="/grades")
        handler = AsyncMock()
        result = await mw(handler, event, _make_data())
        handler.assert_not_called()

    async def test_no_from_user(self):
        from middlewares.access import AccessControlMiddleware
        mw = AccessControlMiddleware()
        event = MagicMock()
        event.from_user = None
        handler = AsyncMock()
        result = await mw(handler, event, {})
        handler.assert_not_called()
