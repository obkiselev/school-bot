"""Per-user throttle middleware — защита от спама (flood control)."""
import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from config import settings

logger = logging.getLogger(__name__)

# Минимальный интервал между запросами одного пользователя (секунды)
_THROTTLE_INTERVAL = 2.0


class ThrottleMiddleware(BaseMiddleware):
    """
    Ограничивает частоту запросов от одного пользователя.

    Исключения:
    - ADMIN_ID — без ограничений
    - Активные FSM-состояния (регистрация, квиз) — без ограничений
    """

    def __init__(self):
        self._last_call: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        user_id = user.id

        # Главный админ — без ограничений
        if settings.ADMIN_ID and user_id == settings.ADMIN_ID:
            return await handler(event, data)

        # Активный FSM — не мешаем пошаговым диалогам
        fsm_context = data.get("state")
        if fsm_context:
            current_state = await fsm_context.get_state()
            if current_state is not None:
                return await handler(event, data)

        now = time.monotonic()
        last = self._last_call.get(user_id, 0.0)

        if now - last < _THROTTLE_INTERVAL:
            remaining = _THROTTLE_INTERVAL - (now - last)
            logger.debug("Throttle: user_id=%d, wait=%.1fs", user_id, remaining)
            if isinstance(event, CallbackQuery):
                await event.answer(
                    f"Не так быстро. Подождите {remaining:.0f} сек.",
                    show_alert=False,
                )
            elif isinstance(event, Message):
                await event.answer(
                    f"Не так быстро. Подождите {remaining:.0f} сек."
                )
            return  # Блокируем запрос

        self._last_call[user_id] = now
        return await handler(event, data)
