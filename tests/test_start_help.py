"""Tests for /help command rendering."""
from unittest.mock import AsyncMock

import pytest

from handlers.start import cmd_help


@pytest.mark.asyncio
async def test_cmd_help_escapes_share_token(monkeypatch):
    async def fake_role(_user_id: int):
        return "student"

    monkeypatch.setattr("handlers.start.get_user_role", fake_role)

    message = AsyncMock()
    message.from_user.id = 123

    await cmd_help(message)

    assert message.answer.await_count == 1
    sent_text = message.answer.await_args.args[0]
    assert "/share &lt;token&gt;" in sent_text
    assert "/share <token>" not in sent_text
