"""Менеджер токенов для автоматического обновления сессии МЭШ."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from database.crud import get_user, update_user_token
from mesh_api.auth import MeshAuth
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

    Использует refresh_token для обновления (без SMS).
    Если refresh_token тоже истёк — бросает AuthenticationError.

    Args:
        user_id: Telegram user ID

    Returns:
        Действующий токен МЭШ

    Raises:
        AuthenticationError: Если пользователь не найден или сессия истекла
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

        # Токен истёк — обновляем через refresh_token
        logger.info("Обновление токена для пользователя user_id=%d", user_id)

        refresh_token = user.get("mesh_refresh_token")
        client_id = user.get("mesh_client_id")
        client_secret = user.get("mesh_client_secret")

        if not refresh_token or not client_id or not client_secret:
            logger.error("Отсутствуют OAuth-данные: user_id=%d", user_id)
            raise AuthenticationError(
                "Сессия истекла. Пожалуйста, перерегистрируйтесь: /start"
            )

        try:
            result = await MeshAuth.do_refresh_token(
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
            )
            new_token = result["token"]
            new_refresh = result.get("refresh_token")

            # Токен МЭШ обычно живёт ~24 часа
            new_expires_at = (datetime.now() + timedelta(hours=24)).isoformat()

        except AuthenticationError:
            # refresh_token тоже истёк — нужна повторная регистрация
            raise
        except Exception as e:
            logger.error("Ошибка обновления токена МЭШ: user_id=%d, error=%s", user_id, e)
            raise AuthenticationError(
                "Не удалось обновить сессию. Перерегистрируйтесь: /start"
            )

        # Сохраняем новый токен в БД
        await update_user_token(
            user_id, new_token, new_expires_at, mesh_refresh_token=new_refresh
        )

        logger.info("Токен обновлён для пользователя user_id=%d", user_id)

        return new_token
