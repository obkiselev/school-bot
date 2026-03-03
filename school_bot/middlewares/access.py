"""Access control middleware — проверка роли и блокировки перед обработкой."""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from config import settings
from database.crud import is_user_allowed

logger = logging.getLogger(__name__)

BLOCKED_MSG = "❗ Доступ ограничен. Обратитесь к администратору."

# Команды, доступные без авторизации
_PUBLIC_COMMANDS = {"/start", "/help"}

# Callback-префиксы, пропускаемые без проверки (регистрация МЭШ, выбор детей)
_PUBLIC_CALLBACK_PREFIXES = (
    "select_child_", "confirm_children_selection", "reregister",
)


class AccessControlMiddleware(BaseMiddleware):
    """Проверяет, что пользователь добавлен админом и не заблокирован.

    - Главный админ (ADMIN_ID) проходит всегда.
    - /start и /help — всегда доступны (для показа "доступ ограничен").
    - FSM-активные пользователи пропускаются (регистрация/квиз в процессе).
    - Callback-и регистрации и квиза пропускаются.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return

        user_id = user.id

        # Главный админ — всегда пропускаем
        if settings.ADMIN_ID and user_id == settings.ADMIN_ID:
            return await handler(event, data)

        # Публичные команды — пропускаем (start покажет "доступ ограничен" сам)
        if isinstance(event, Message) and event.text:
            cmd = event.text.split()[0].lower() if event.text.startswith("/") else None
            # Убираем суффикс бота (/start@botname → /start)
            if cmd and "@" in cmd:
                cmd = cmd.split("@")[0]
            if cmd in _PUBLIC_COMMANDS:
                return await handler(event, data)

        # Callback-и регистрации — пропускаем
        if isinstance(event, CallbackQuery) and event.data:
            if event.data.startswith(_PUBLIC_CALLBACK_PREFIXES):
                return await handler(event, data)

        # FSM — если пользователь в процессе (регистрация или квиз), пропускаем
        fsm_context = data.get("state")
        if fsm_context:
            current_state = await fsm_context.get_state()
            if current_state is not None:
                return await handler(event, data)

        # Проверка в БД
        try:
            allowed, role = await is_user_allowed(user_id)
        except Exception:
            logger.exception("DB error in access middleware — fail-closed for user %s", user_id)
            await self._deny(event)
            return

        if allowed:
            return await handler(event, data)

        # Заблокирован или не найден
        await self._deny(event)

    async def _deny(self, event: TelegramObject) -> None:
        """Отправить сообщение об ограничении доступа."""
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
