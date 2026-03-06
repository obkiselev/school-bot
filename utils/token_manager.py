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


async def _reauth_with_credentials(user_id: int, login: str, password: str) -> str:
    """
    Переавторизация через сохранённые логин/пароль.

    Если вход проходит без SMS — сохраняет новый токен + OAuth-данные.
    Если требуется SMS — бросает AuthenticationError (нужна ручная перерегистрация).

    Returns:
        Новый mesh_token

    Raises:
        AuthenticationError: Если нужен SMS или ошибка авторизации
    """
    logger.info("Авто-переавторизация через сохранённые данные для user_id=%d", user_id)

    auth = MeshAuth()
    try:
        result = await auth.start_login(login, password)
    except AuthenticationError:
        raise
    except Exception as e:
        logger.error("Ошибка авто-переавторизации: user_id=%d, error=%s", user_id, e)
        raise AuthenticationError(
            "Не удалось автоматически обновить сессию. Перерегистрируйтесь: /start"
        )

    if result.get("status") == "sms_required":
        logger.warning(
            "Авто-переавторизация требует SMS для user_id=%d. "
            "Пользователь должен перерегистрироваться.",
            user_id,
        )
        raise AuthenticationError(
            "Сессия МЭШ истекла. Требуется SMS-подтверждение.\n"
            "Пожалуйста, перерегистрируйтесь: /start"
        )

    new_token = result["token"]
    new_refresh = result.get("refresh_token")
    new_client_id = result.get("client_id")
    new_client_secret = result.get("client_secret")
    new_expires_at = (datetime.now() + timedelta(hours=24)).isoformat()

    await update_user_token(
        user_id, new_token, new_expires_at,
        mesh_refresh_token=new_refresh,
        mesh_client_id=new_client_id,
        mesh_client_secret=new_client_secret,
    )

    if not new_refresh or not new_client_id or not new_client_secret:
        logger.warning(
            "Авто-переавторизация для user_id=%d: НЕПОЛНЫЕ OAuth-данные! "
            "refresh=%s, client_id=%s, client_secret=%s. "
            "Вероятно Playwright fallback — следующее обновление токена "
            "потребует полной переавторизации.",
            user_id,
            "YES" if new_refresh else "NO",
            "YES" if new_client_id else "NO",
            "YES" if new_client_secret else "NO",
        )
    else:
        logger.info(
            "Авто-переавторизация успешна для user_id=%d, "
            "refresh=%s, client_id=%s, client_secret=%s",
            user_id,
            "YES" if new_refresh else "NO",
            "YES" if new_client_id else "NO",
            "YES" if new_client_secret else "NO",
        )

    return new_token


async def ensure_token(user_id: int) -> str:
    """
    Получает действующий токен для пользователя.

    Порядок:
    1. Если текущий токен валиден — возвращает его
    2. Если есть OAuth-данные — обновляет через refresh_token
    3. Если OAuth-данных нет — переавторизация через сохранённый логин/пароль
    4. Если всё не удалось — бросает AuthenticationError

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

        # Токен истёк — обновляем
        logger.info("Обновление токена для пользователя user_id=%d", user_id)

        refresh_token = user.get("mesh_refresh_token")
        client_id = user.get("mesh_client_id")
        client_secret = user.get("mesh_client_secret")

        # Способ 1: OAuth refresh (если есть данные)
        if refresh_token and client_id and client_secret:
            try:
                result = await MeshAuth.do_refresh_token(
                    refresh_token=refresh_token,
                    client_id=client_id,
                    client_secret=client_secret,
                )
                new_token = result["token"]
                new_refresh = result.get("refresh_token")
                new_expires_at = (datetime.now() + timedelta(hours=24)).isoformat()

                await update_user_token(
                    user_id, new_token, new_expires_at,
                    mesh_refresh_token=new_refresh,
                )

                logger.info("Токен обновлён через refresh_token для user_id=%d", user_id)
                return new_token

            except AuthenticationError:
                # refresh_token истёк — попробуем переавторизацию
                logger.warning(
                    "refresh_token истёк для user_id=%d, пробуем переавторизацию",
                    user_id,
                )
            except Exception as e:
                logger.error(
                    "Ошибка OAuth refresh: user_id=%d, error=%s. Пробуем переавторизацию.",
                    user_id, e,
                )

        # Способ 2: Переавторизация через сохранённые логин/пароль
        login = user.get("mesh_login")
        password = user.get("mesh_password")

        if login and password:
            return await _reauth_with_credentials(user_id, login, password)

        # Ничего не помогло
        logger.error(
            "Токен истёк, нет OAuth-данных и нет сохранённых учётных данных. user_id=%d",
            user_id,
        )
        raise AuthenticationError(
            "Сессия МЭШ истекла. Пожалуйста, перерегистрируйтесь: /start"
        )
