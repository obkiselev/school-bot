import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from bot.config import ADMIN_ID
from bot.db.queries import is_user_allowed
from bot.states.quiz_states import QuizFlow

logger = logging.getLogger(__name__)

BLOCKED_MSG = "❗ Доступ ограничен. Обратитесь к администратору."

QUIZ_STATES = {
    QuizFlow.answering_question.state,
    QuizFlow.answering_matching_sub.state,
}


class AccessControlMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return  # no user info (e.g. channel post) — block

        user_id = user.id

        # Short-circuit: primary admin always allowed
        if ADMIN_ID is not None and user_id == ADMIN_ID:
            return await handler(event, data)

        # DB lookup with fail-closed
        try:
            allowed, role = await is_user_allowed(user_id)
        except Exception:
            logger.exception("DB error in access control middleware — fail-closed for user %s", user_id)
            await self._deny(event)
            return

        if allowed:
            return await handler(event, data)

        # User is blocked or not found — check for mid-quiz soft block
        if role is not None:
            # User exists but is blocked — check if mid-quiz
            state = data.get("state")
            if state:
                current_state = await state.get_state()
                if current_state in QUIZ_STATES:
                    if self._is_quiz_action(event):
                        return await handler(event, data)

        await self._deny(event)

    def _is_quiz_action(self, event: TelegramObject) -> bool:
        """Check if the action is quiz-related (answer callback or text message)."""
        if isinstance(event, CallbackQuery):
            return event.data is not None and event.data.startswith("ans:")
        if isinstance(event, Message):
            # Allow plain text answers only (not commands)
            return event.text is not None and not event.text.startswith("/")
        return False

    async def _deny(self, event: TelegramObject) -> None:
        """Send denial message and dismiss callback spinner if needed."""
        if isinstance(event, CallbackQuery):
            try:
                await event.message.answer(BLOCKED_MSG)
            except Exception:
                pass
            try:
                await event.answer()
            except Exception:
                pass
        elif isinstance(event, Message):
            try:
                await event.answer(BLOCKED_MSG)
            except Exception:
                pass
