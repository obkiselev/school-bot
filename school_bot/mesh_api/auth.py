"""Authentication handler for МЭШ API via OctoDiary."""
import asyncio
import logging
from typing import Optional, Dict, Any

from octodiary.apis.async_ import AsyncMobileAPI
from octodiary.urls import Systems
from octodiary.types.enter_sms_code import EnterSmsCode
from octodiary.exceptions import APIError

from .exceptions import AuthenticationError, NetworkError

# Таймаут ожидания ответа от МЭШ (секунды)
_AUTH_TIMEOUT = 20

logger = logging.getLogger(__name__)


# Хранилище незавершённых сессий авторизации (ожидание SMS-кода).
# Ключ — Telegram user_id, значение — объект MeshAuth с открытой сессией.
# Очищается после завершения авторизации или по таймауту.
_pending_auth: Dict[int, "MeshAuth"] = {}


def get_pending_auth(user_id: int) -> Optional["MeshAuth"]:
    """Получить незавершённую сессию авторизации для пользователя."""
    return _pending_auth.get(user_id)


def clear_pending_auth(user_id: int) -> None:
    """Удалить незавершённую сессию авторизации."""
    _pending_auth.pop(user_id, None)


class MeshAuth:
    """Handles authentication with МЭШ API via OctoDiary."""

    def __init__(self):
        self.api = AsyncMobileAPI(system=Systems.MES)
        self._pending_sms: Optional[EnterSmsCode] = None

    async def _close_api_session(self) -> None:
        """Закрыть незавершённую aiohttp-сессию octodiary (после таймаута/ошибки)."""
        try:
            session = getattr(self.api, "_login_info", {}).get("session")
            if session and not session.closed:
                await session.close()
        except Exception:
            pass

    async def start_login(self, login: str, password: str) -> Dict[str, Any]:
        """
        Начинает авторизацию. Может потребоваться SMS-код.

        Returns:
            {"status": "sms_required", "contact": "7***99", "ttl": 300}
            или
            {"status": "ok", "token": "...", ...}

        Raises:
            AuthenticationError: Неверные учётные данные
            NetworkError: Ошибка сети
        """
        try:
            result = await asyncio.wait_for(
                self.api.login(username=login, password=password),
                timeout=_AUTH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("Таймаут авторизации в МЭШ (>%ds)", _AUTH_TIMEOUT)
            await self._close_api_session()
            self.api = AsyncMobileAPI(system=Systems.MES)  # сброс для следующей попытки
            raise NetworkError("Сервер МЭШ не отвечает. Попробуйте позже.")
        except APIError as e:
            await self._close_api_session()
            self.api = AsyncMobileAPI(system=Systems.MES)
            if e.error_types in ("InvalidCredentials", "NotFound"):
                raise AuthenticationError("Неверный логин или пароль")
            elif e.error_types == "TemporarilyBlocked":
                raise AuthenticationError(
                    "Аккаунт временно заблокирован. Попробуйте позже."
                )
            else:
                logger.error("Ошибка API при входе: %s", e)
                raise NetworkError(f"Ошибка входа: {e}")
        except Exception as e:
            await self._close_api_session()
            self.api = AsyncMobileAPI(system=Systems.MES)
            logger.error("Сетевая ошибка при входе: %s", e)
            raise NetworkError(f"Ошибка сети при входе: {e}")

        if isinstance(result, EnterSmsCode):
            self._pending_sms = result
            return {
                "status": "sms_required",
                "contact": result.contact,
                "ttl": result.ttl,
            }

        # Прямой вход без SMS (редко для МЭШ)
        return await self._finalize_auth(result)

    async def verify_sms(self, code: str) -> Dict[str, Any]:
        """
        Завершает авторизацию с SMS-кодом.

        Returns:
            {"status": "ok", "token": "...", ...}

        Raises:
            AuthenticationError: Неверный или истёкший SMS-код
        """
        if not self._pending_sms:
            raise AuthenticationError("Нет ожидающего SMS-подтверждения")

        try:
            token = await self._pending_sms.async_enter_code(code)
        except APIError as e:
            if e.error_types == "InvalidOTP":
                raise AuthenticationError("Неверный SMS-код. Попробуйте ещё раз.")
            elif e.error_types == "CodeExpired":
                raise AuthenticationError(
                    "SMS-код истёк. Начните регистрацию заново: /start"
                )
            elif e.error_types == "NoAttempts":
                raise AuthenticationError(
                    "Исчерпаны попытки ввода кода. Начните заново: /start"
                )
            else:
                logger.error("Ошибка SMS-верификации: %s", e)
                raise AuthenticationError(f"Ошибка верификации: {e}")
        except Exception as e:
            logger.error("Ошибка при вводе SMS-кода: %s", e)
            raise NetworkError(f"Ошибка сети при верификации: {e}")

        self._pending_sms = None
        return await self._finalize_auth(token)

    async def _finalize_auth(self, token: str) -> Dict[str, Any]:
        """
        Получает профиль и данные о детях после успешной авторизации.

        Returns:
            {
                "status": "ok",
                "token": str,
                "profile_id": int,
                "mes_role": str,
                "children": list,
                "refresh_token": str | None,
                "client_id": str | None,
                "client_secret": str | None,
            }
        """
        self.api.token = token

        try:
            profiles = await self.api.get_users_profile_info()
        except Exception as e:
            logger.error("Ошибка получения профиля: %s", e)
            raise NetworkError(f"Ошибка получения профиля: {e}")

        if not profiles:
            raise AuthenticationError("Профиль не найден")

        profile_id = profiles[0].id
        mes_role = profiles[0].type

        try:
            family = await self.api.get_family_profile(profile_id=profile_id)
        except Exception as e:
            logger.error("Ошибка получения семейного профиля: %s", e)
            raise NetworkError(f"Ошибка получения семейного профиля: {e}")

        children = family.children or []

        return {
            "status": "ok",
            "token": token,
            "profile_id": profile_id,
            "mes_role": mes_role,
            "children": children,
            "refresh_token": getattr(self.api, "token_for_refresh", None),
            "client_id": getattr(self.api, "client_id", None),
            "client_secret": getattr(self.api, "client_secret", None),
        }

    @staticmethod
    async def do_refresh_token(
        refresh_token: str,
        client_id: str,
        client_secret: str,
    ) -> Dict[str, Any]:
        """
        Обновляет токен без повторной авторизации (без SMS).

        Returns:
            {"token": str, "refresh_token": str | None}

        Raises:
            AuthenticationError: Если refresh_token истёк
        """
        api = AsyncMobileAPI(system=Systems.MES)

        try:
            new_token = await api.refresh_token(
                token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
            )
        except Exception as e:
            logger.error("Ошибка обновления токена: %s", e)
            raise AuthenticationError(
                "Сессия истекла. Пожалуйста, перерегистрируйтесь: /start"
            )

        return {
            "token": new_token,
            "refresh_token": getattr(api, "token_for_refresh", None),
        }
