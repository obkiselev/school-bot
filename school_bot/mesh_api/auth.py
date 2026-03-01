"""Authentication handler for МЭШ API via OctoDiary."""
import asyncio
import logging
from typing import Optional, Dict, Any, Callable, Awaitable

from octodiary.apis.async_ import AsyncMobileAPI
from octodiary.urls import Systems
from octodiary.types.enter_sms_code import EnterSmsCode
from octodiary.exceptions import APIError

from .exceptions import AuthenticationError, NetworkError

# Таймаут одной попытки start_login (шаги 1–4 на login.mos.ru).
# curl_cffi + Chrome TLS: шаги занимают < 0.5с суммарно. 10с — запас на нестабильную сеть.
_LOGIN_TIMEOUT = 10
# Таймаут verify_sms (шаг 5 на school.mos.ru может быть медленным).
_SMS_TIMEOUT = 90
# Максимальное число попыток start_login при сетевой ошибке/таймауте.
# При rate-limit дополнительный retry только продлевает блокировку.
_AUTH_RETRIES = 1

# TCP pre-check: быстрая проверка доступности login.mos.ru перед авторизацией.
_LOGIN_HOST = "login.mos.ru"
_LOGIN_PORT = 443
_TCP_CHECK_TIMEOUT = 5  # секунд


async def _check_server_reachable() -> bool:
    """Быстрая TCP-проверка login.mos.ru:443 перед авторизацией.

    Возвращает True если сервер принимает TCP-соединения, False иначе.
    Позволяет сразу определить недоступность сервера без ожидания _LOGIN_TIMEOUT.
    """
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(_LOGIN_HOST, _LOGIN_PORT),
            timeout=_TCP_CHECK_TIMEOUT,
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception as e:
        logger.debug("TCP pre-check %s:%d failed: %s", _LOGIN_HOST, _LOGIN_PORT, e)
        return False

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

    async def start_login(
        self,
        login: str,
        password: str,
        on_retry: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        Начинает авторизацию. Может потребоваться SMS-код.

        Args:
            login: Логин МЭШ (mos.ru)
            password: Пароль
            on_retry: Опциональный callback (attempt, total) → None, вызывается перед повторной попыткой

        Returns:
            {"status": "sms_required", "contact": "7***99", "ttl": 300}
            или
            {"status": "ok", "token": "...", ...}

        Raises:
            AuthenticationError: Неверные учётные данные
            NetworkError: Ошибка сети
        """
        # Быстрая TCP-проверка доступности сервера.
        tcp_ok = await _check_server_reachable()
        if tcp_ok:
            logger.info("TCP pre-check %s:%d: OK", _LOGIN_HOST, _LOGIN_PORT)
        else:
            logger.warning("TCP pre-check %s:%d: FAIL (нет TCP-соединения)", _LOGIN_HOST, _LOGIN_PORT)
            raise NetworkError(
                f"Сервер {_LOGIN_HOST} недоступен (нет TCP-соединения). "
                "Попробуйте позже."
            )

        result = None
        for attempt in range(1, _AUTH_RETRIES + 1):
            try:
                result = await asyncio.wait_for(
                    self.api.login(username=login, password=password),
                    timeout=_LOGIN_TIMEOUT,
                )
                break  # успех — выходим из цикла
            except asyncio.TimeoutError:
                logger.warning(
                    "Попытка %d/%d: таймаут авторизации МЭШ (>%ds)",
                    attempt, _AUTH_RETRIES, _LOGIN_TIMEOUT,
                )
                await self._close_api_session()
                self.api = AsyncMobileAPI(system=Systems.MES)
                if attempt < _AUTH_RETRIES:
                    if on_retry:
                        await on_retry(attempt, _AUTH_RETRIES)
                    await asyncio.sleep(5)
                else:
                    raise NetworkError(
                        "Сервер принимает соединения, но не отвечает на запросы. "
                        "Возможно, ваш IP временно ограничен. "
                        "Подождите 30-60 минут и попробуйте снова."
                    )
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
                logger.error("Сетевая ошибка при входе (попытка %d): %s", attempt, e)
                if attempt < _AUTH_RETRIES:
                    if on_retry:
                        await on_retry(attempt, _AUTH_RETRIES)
                    await asyncio.sleep(5)
                else:
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
            token = await asyncio.wait_for(
                self._pending_sms.async_enter_code(code),
                timeout=_SMS_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("Таймаут при верификации SMS-кода (>%ds)", _SMS_TIMEOUT)
            await self._close_api_session()
            raise NetworkError("Сервер МЭШ не отвечает. Попробуйте ввести код ещё раз.")
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


# ─── Трёхуровневая авторизация: patchright → playwright+stealth → curl_cffi ──
# PlaywrightMeshAuth (со стелсом) — основной метод.
# Если браузер не может загрузить страницу — автоматический откат на curl_cffi.

_CurlCffiMeshAuth = MeshAuth  # Сохраняем оригинальный класс (curl_cffi)

_has_playwright = False
try:
    from .playwright_auth import PlaywrightMeshAuth
    _has_playwright = True
    logger.info("Playwright-авторизация доступна (stealth + fallback на curl_cffi)")
except ImportError:
    logger.warning(
        "Playwright/patchright не найден — используется только curl_cffi. "
        "Для установки: pip install patchright && patchright install chromium"
    )


class HybridMeshAuth:
    """Пробует PlaywrightMeshAuth, при неудаче — откат на curl_cffi MeshAuth.

    Откат происходит во время работы (не только при импорте): если браузер
    запустился, но страница не загрузилась (about:blank) — переключаемся
    на HTTP-подход через curl_cffi/OctoDiary.
    """

    def __init__(self):
        self._impl = None

    async def start_login(self, login, password, on_retry=None):
        # Пробуем Playwright со стелсом
        if _has_playwright:
            try:
                self._impl = PlaywrightMeshAuth()
                return await self._impl.start_login(login, password, on_retry)
            except NetworkError as e:
                error_msg = str(e).lower()
                if "не загрузилась" in error_msg or "not loaded" in error_msg:
                    logger.warning(
                        "Playwright не смог загрузить страницу, "
                        "переключаемся на curl_cffi: %s", e,
                    )
                    # Продолжаем к curl_cffi fallback
                else:
                    raise
            except Exception as e:
                logger.warning("Playwright ошибка, пробуем curl_cffi: %s", e)

        # Fallback: curl_cffi через OctoDiary
        logger.info("Используем curl_cffi fallback для авторизации")
        self._impl = _CurlCffiMeshAuth()
        return await self._impl.start_login(login, password, on_retry)

    async def verify_sms(self, code):
        if not self._impl:
            raise AuthenticationError("Нет активной сессии авторизации")
        return await self._impl.verify_sms(code)

    @staticmethod
    async def do_refresh_token(refresh_token, client_id, client_secret):
        # Обновление токена всегда через HTTP (без браузера)
        return await _CurlCffiMeshAuth.do_refresh_token(
            refresh_token, client_id, client_secret,
        )


MeshAuth = HybridMeshAuth  # type: ignore[misc]
