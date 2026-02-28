"""Менеджер токенов для автоматического обновления сессии МЭШ."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from database.crud import get_user, update_user_token
from mesh_api.client import MeshClient
from mesh_api.exceptions import AuthenticationError, MeshAPIError

logger = logging.getLogger(__name__)

# Буфер безопасности — обновляем токен за 5 минут до истечения
TOKEN_EXPIRY_BUFFER_MINUTES = 5

# Блокировки по user_id — защита от одновременного обновления токена
_token_locks: dict[int, asyncio.Lock] = {}


def _is_token_valid(token_expires_at: Optional[str]) -> bool:
    """
    Проверяет, действителен ли токен с учётом буфера безопасности.

    Args:
        token_expires_at: ISO-строка срока действия токена или None

    Returns:
        True если токен ещё действителен, False если истёк или None
    """
    # Токен ещё не получен — считаем истёкшим
    if token_expires_at is None:
        return False

    try:
        expires_at = datetime.fromisoformat(token_expires_at)
    except (ValueError, TypeError):
        # Невалидный формат — считаем токен истёкшим
        logger.warning("Невалидный формат token_expires_at: %s", token_expires_at)
        return False

    # Сравниваем naive datetime с naive datetime (без timezone)
    # Буфер: считаем истёкшим за 5 минут до реального срока
    buffer = timedelta(minutes=TOKEN_EXPIRY_BUFFER_MINUTES)
    return (expires_at - buffer) > datetime.now()


async def ensure_token(user_id: int) -> str:
    """
    Получает действующий токен для пользователя.

    Проверяет текущий токен, при необходимости обновляет через МЭШ API.
    Использует asyncio.Lock per user_id для защиты от гонки при параллельных вызовах.

    Args:
        user_id: Telegram user ID

    Returns:
        Действующий токен МЭШ

    Raises:
        AuthenticationError: Если пользователь не найден или аутентификация не удалась
        MeshAPIError: Если произошла ошибка API или сети
    """
    # Блокировка по user_id — только один вызов обновляет токен одновременно
    if user_id not in _token_locks:
        _token_locks[user_id] = asyncio.Lock()

    async with _token_locks[user_id]:
        # Получаем данные пользователя из БД
        user = await get_user(user_id)

        if not user:
            logger.error("Пользователь не найден: user_id=%d", user_id)
            raise AuthenticationError("Пользователь не зарегистрирован")

        # Проверяем, действителен ли текущий токен
        current_token = user.get("mesh_token")
        token_expires_at = user.get("token_expires_at")

        if current_token and _is_token_valid(token_expires_at):
            return current_token

        # Токен истёк или отсутствует — обновляем
        logger.info("Обновление токена для пользователя user_id=%d", user_id)

        login = user.get("mesh_login")
        password = user.get("mesh_password")

        if not login or not password:
            logger.error("Отсутствуют учётные данные: user_id=%d", user_id)
            raise AuthenticationError("Учётные данные не найдены")

        # Аутентификация через МЭШ API с обязательным закрытием клиента
        client = MeshClient()
        try:
            auth_result = await client.authenticate(login, password)
            new_token = auth_result["token"]
            new_expires_at = auth_result["expires_at"]
        except MeshAPIError:
            logger.error("Ошибка обновления токена МЭШ: user_id=%d", user_id)
            raise
        finally:
            await client.close()

        # Сохраняем новый токен в БД
        await update_user_token(user_id, new_token, new_expires_at)

        logger.info("Токен обновлён для пользователя user_id=%d", user_id)

        return new_token
