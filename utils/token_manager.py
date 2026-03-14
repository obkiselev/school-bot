"""Token manager for safe MeSH session reuse and refresh."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from database.crud import get_user, update_user_token
from mesh_api.auth import MeshAuth
from mesh_api.exceptions import AuthenticationError

logger = logging.getLogger(__name__)

TOKEN_EXPIRY_BUFFER_MINUTES = 5
FORCED_INVALIDATION_SENTINEL = "2000-01-01T00:00:00"

_token_locks: dict[int, asyncio.Lock] = {}


def _has_oauth_refresh_data(user: dict) -> bool:
    """Return True when the user has a full OAuth refresh bundle."""
    return bool(
        user.get("mesh_refresh_token")
        and user.get("mesh_client_id")
        and user.get("mesh_client_secret")
    )


def _is_token_valid(token_expires_at: Optional[str]) -> bool:
    """
    Check whether the token is still valid with a small safety buffer.

    Returns False when the expiry is missing or malformed.
    """
    if token_expires_at is None:
        return False

    try:
        expires_at = datetime.fromisoformat(token_expires_at)
    except (ValueError, TypeError):
        logger.warning("Invalid token_expires_at format: %s", token_expires_at)
        return False

    buffer = timedelta(minutes=TOKEN_EXPIRY_BUFFER_MINUTES)
    return (expires_at - buffer) > datetime.now()


def _is_forced_refresh(token_expires_at: Optional[str]) -> bool:
    """Return True when the token was explicitly invalidated after a real 401."""
    return token_expires_at == FORCED_INVALIDATION_SENTINEL


async def ensure_token(user_id: int) -> str:
    """
    Return a usable MeSH token for the user.

    Rules:
    1. A still-valid token is reused.
    2. OAuth sessions are refreshed via refresh_token.
    3. Fallback sessions without OAuth are reused until the first real 401.
    4. After a real 401 or failed OAuth refresh, we do not trigger silent SMS login.
    """
    if user_id not in _token_locks:
        _token_locks[user_id] = asyncio.Lock()

    async with _token_locks[user_id]:
        user = await get_user(user_id)
        if not user:
            logger.error("User not found: user_id=%d", user_id)
            raise AuthenticationError("Пользователь не зарегистрирован")

        current_token = user.get("mesh_token")
        token_expires_at = user.get("token_expires_at")
        has_oauth_refresh = _has_oauth_refresh_data(user)
        forced_refresh = _is_forced_refresh(token_expires_at)

        if current_token and _is_token_valid(token_expires_at):
            return current_token

        logger.info("Refreshing MeSH token for user_id=%d", user_id)

        # For fallback sessions we no longer trust the local 24h timer. Reuse the token
        # until MeSH itself returns 401, then require a manual /start instead of SMS spam.
        if current_token and not has_oauth_refresh and not forced_refresh:
            logger.info(
                "Reusing fallback token without OAuth data for user_id=%d until a real 401",
                user_id,
            )
            return current_token

        if current_token and not has_oauth_refresh and forced_refresh:
            logger.warning(
                "Fallback token is exhausted for user_id=%d; silent SMS relogin is disabled",
                user_id,
            )
            raise AuthenticationError(
                "Сессия МЭШ истекла. Без OAuth refresh_token бот не запускает новый SMS-вход автоматически.\n"
                "Пожалуйста, перерегистрируйтесь: /start"
            )

        refresh_token = user.get("mesh_refresh_token")
        client_id = user.get("mesh_client_id")
        client_secret = user.get("mesh_client_secret")

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
                    user_id,
                    new_token,
                    new_expires_at,
                    mesh_refresh_token=new_refresh,
                )

                logger.info("Token refreshed via refresh_token for user_id=%d", user_id)
                return new_token
            except AuthenticationError:
                logger.warning(
                    "refresh_token failed for user_id=%d; silent SMS relogin is disabled",
                    user_id,
                )
            except Exception as e:
                logger.error(
                    "OAuth refresh error for user_id=%d: %s. Silent SMS relogin is disabled.",
                    user_id,
                    e,
                )

            raise AuthenticationError(
                "Не удалось автоматически обновить сессию МЭШ через refresh_token. "
                "Чтобы не вызывать лишние SMS-коды, бот не запускает повторный вход сам.\n"
                "Пожалуйста, перерегистрируйтесь: /start"
            )

        logger.error(
            "Token expired and no OAuth refresh data is available for user_id=%d",
            user_id,
        )
        raise AuthenticationError(
            "Сессия МЭШ истекла. Пожалуйста, перерегистрируйтесь: /start"
        )
