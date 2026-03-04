"""Authentication handler for МЭШ API via OctoDiary."""
import asyncio
import logging
import time
from typing import Optional, Dict, Any, Callable, Awaitable

from octodiary.apis.async_ import AsyncMobileAPI, AsyncWebAPI
from octodiary.urls import Systems
from octodiary.types.enter_sms_code import EnterSmsCode
from octodiary.exceptions import APIError

from .exceptions import AuthenticationError, NetworkError

logger = logging.getLogger(__name__)

# Таймаут одной попытки start_login (5 шагов на login.mos.ru).
# Каждый шаг = TLS-хэндшейк (BoringSSL) + HTTP-запрос.
# На медленной сети один TLS-хэндшейк может занимать 5-10с → 60с на все 5 шагов.
_LOGIN_TIMEOUT = 60
# Таймаут verify_sms (шаг 5 на school.mos.ru может быть медленным).
_SMS_TIMEOUT = 90
# Максимальное число попыток start_login при сетевой ошибке/таймауте.
# При rate-limit дополнительный retry только продлевает блокировку.
_AUTH_RETRIES = 1

# TCP pre-check: быстрая проверка доступности login.mos.ru перед авторизацией.
_LOGIN_HOST = "login.mos.ru"
_LOGIN_PORT = 443
_TCP_CHECK_TIMEOUT = 5  # секунд


async def _check_server_reachable(proxy_url: str = None) -> bool:
    """Быстрая TCP-проверка доступности перед авторизацией.

    Если proxy_url задан — проверяет доступность прокси-сервера.
    Иначе — проверяет login.mos.ru:443 напрямую.
    """
    if proxy_url:
        from urllib.parse import urlparse
        parsed = urlparse(proxy_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (1080 if "socks" in (parsed.scheme or "") else 8080)
        label = f"proxy {host}:{port}"
    else:
        host = _LOGIN_HOST
        port = _LOGIN_PORT
        label = f"{_LOGIN_HOST}:{_LOGIN_PORT}"

    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=_TCP_CHECK_TIMEOUT,
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception as e:
        logger.debug("TCP pre-check %s failed: %s", label, e)
        return False


_CURL_TLS_TIMEOUT = 15  # секунд на TLS-проверку через curl_cffi


async def _check_curl_cffi_tls(proxy_url: str = None) -> bool:
    """Быстрая TLS-проверка через curl_cffi: GET https://login.mos.ru/.

    Проверяет что curl_cffi с Chrome TLS impersonation может пройти
    TLS-хэндшейк. Если нет — нет смысла ждать полный _LOGIN_TIMEOUT.
    """
    try:
        from curl_cffi.requests import AsyncSession
        kwargs = {"impersonate": "chrome124", "timeout": _CURL_TLS_TIMEOUT}
        if proxy_url:
            kwargs["proxy"] = proxy_url
        async with AsyncSession(**kwargs) as s:
            import time
            t0 = time.monotonic()
            resp = await s.get(f"https://{_LOGIN_HOST}/")
            elapsed = time.monotonic() - t0
            logger.info(
                "curl_cffi TLS pre-check: HTTP %d за %.1fс (proxy=%s)",
                resp.status_code, elapsed, "yes" if proxy_url else "direct",
            )
            return True
    except ImportError:
        logger.debug("curl_cffi не установлен, пропускаем TLS pre-check")
        return True  # если curl_cffi нет — пусть OctoDiary сам разберётся
    except Exception as e:
        logger.warning("curl_cffi TLS pre-check failed: %s", e)
        return False


# Хранилище незавершённых сессий авторизации (ожидание SMS-кода).
# Ключ — Telegram user_id, значение — объект MeshAuth с открытой сессией.
# Очищается после завершения авторизации или по таймауту.
_pending_auth: Dict[int, "MeshAuth"] = {}

# Кулдаун между попытками авторизации (защита от "долбёжки" сервера)
_AUTH_COOLDOWN_SECONDS = 60
_last_auth_attempt: Dict[int, float] = {}


def check_auth_cooldown(user_id: int) -> Optional[int]:
    """Проверить кулдаун авторизации для пользователя.

    Returns:
        None если можно продолжать, или число оставшихся секунд.
    """
    last = _last_auth_attempt.get(user_id)
    if last is None:
        return None
    remaining = _AUTH_COOLDOWN_SECONDS - (time.monotonic() - last)
    if remaining <= 0:
        return None
    return int(remaining) + 1


def record_auth_attempt(user_id: int) -> None:
    """Записать попытку авторизации для кулдауна."""
    _last_auth_attempt[user_id] = time.monotonic()


def get_pending_auth(user_id: int) -> Optional["MeshAuth"]:
    """Получить незавершённую сессию авторизации для пользователя."""
    return _pending_auth.get(user_id)


def clear_pending_auth(user_id: int) -> None:
    """Удалить незавершённую сессию авторизации."""
    _pending_auth.pop(user_id, None)


def _make_web_api(mobile_api: AsyncMobileAPI) -> AsyncWebAPI:
    """Создаёт AsyncWebAPI с тем же токеном и прокси что у mobile_api."""
    web_api = AsyncWebAPI(system=Systems.MES)
    web_api.token = mobile_api.token
    proxy = getattr(mobile_api, "_socks_proxy", None)
    if proxy:
        web_api._socks_proxy = proxy
    return web_api


async def _finalize_profile_and_children(api: AsyncMobileAPI):
    """Общая логика получения профиля и детей после авторизации.

    Для родительских аккаунтов: get_users_profile_info() + get_family_profile().
    Для ученических аккаунтов (403 на profile_info): get_session_info() +
    get_student_profiles() как fallback.

    Args:
        api: Настроенный AsyncMobileAPI с установленным token и прокси.

    Returns:
        (profile_id, mes_role, children) — данные профиля и список детей.
    """
    profile_id = None
    mes_role = None
    is_student_fallback = False

    # Шаг 1: пробуем get_users_profile_info (работает для родителей/учителей)
    try:
        profiles = await api.get_users_profile_info()
        if profiles:
            profile_id = profiles[0].id
            mes_role = profiles[0].type
    except Exception as e:
        error_str = str(e)
        if "403" in error_str or "access_denied" in error_str:
            logger.info(
                "get_users_profile_info вернул 403 — вероятно ученический аккаунт, "
                "переключаемся на get_session_info"
            )
            is_student_fallback = True
        else:
            logger.error("Ошибка получения профиля: %s", e)
            raise NetworkError(f"Ошибка получения профиля: {e}")

    # Шаг 1б: fallback для учеников — get_session_info (AsyncWebAPI)
    session_info = None
    if is_student_fallback or not profile_id:
        try:
            web_api = _make_web_api(api)
            session_info = await web_api.get_session_info()
            if session_info and session_info.profiles:
                profile_id = session_info.profiles[0].id
                mes_role = session_info.profiles[0].type
                logger.info(
                    "get_session_info: profile_id=%s, type=%s",
                    profile_id, mes_role,
                )
            else:
                raise NetworkError("Профиль не найден в данных сессии")
        except NetworkError:
            raise
        except Exception as e:
            logger.error("Ошибка получения session_info: %s", e)
            raise NetworkError(f"Ошибка получения профиля (fallback): {e}")

    if not profile_id:
        raise AuthenticationError("Профиль не найден")

    # Шаг 2: получаем данные о детях
    children = []
    try:
        family = await api.get_family_profile(profile_id=profile_id)
        children = family.children or []
    except Exception as e:
        if is_student_fallback:
            # Для ученика get_family_profile тоже может вернуть 403 — это нормально
            logger.info(
                "get_family_profile не удался для ученика (ожидаемо): %s, "
                "строим профиль из session_info + student_profiles",
                e,
            )
        else:
            logger.error("Ошибка получения семейного профиля: %s", e)
            raise NetworkError(f"Ошибка получения семейного профиля: {e}")

    # Шаг 3: если children пуст и это ученик — строим из get_student_profiles
    if not children and is_student_fallback and session_info:
        children = await _build_student_child(api, profile_id, session_info)

    return profile_id, mes_role, children


async def _build_student_child(api: AsyncMobileAPI, profile_id, session_info):
    """Строит список из одного 'ребёнка' для ученического аккаунта.

    Ученик сам является ребёнком. Собираем Child-объект из данных
    SessionUserInfo и (опционально) StudentProfile.
    """
    from octodiary.types.mobile.family_profile import Child, School

    # Базовые данные из session_info
    child = Child(
        id=profile_id,
        first_name=session_info.first_name,
        last_name=session_info.last_name,
        middle_name=session_info.middle_name,
        contingent_guid=session_info.person_id,
    )

    # Обогащаем данными из get_student_profiles (класс, школа) — AsyncWebAPI
    try:
        web_api = _make_web_api(api)
        student_profiles = await web_api.get_student_profiles(
            profile_id=profile_id,
            profile_type="student",
        )
        if student_profiles:
            sp = student_profiles[0] if isinstance(student_profiles, list) else student_profiles
            child.id = getattr(sp, "id", None) or child.id
            child.first_name = getattr(sp, "first_name", None) or child.first_name
            child.last_name = getattr(sp, "last_name", None) or child.last_name
            child.middle_name = getattr(sp, "middle_name", None) or child.middle_name
            child.contingent_guid = getattr(sp, "person_id", None) or child.contingent_guid
            if sp.class_unit:
                child.class_name = sp.class_unit.name
                child.class_unit_id = sp.class_unit.id
            if sp.school_id:
                child.school = School(id=sp.school_id)
            logger.info(
                "StudentProfile: id=%s, class=%s, person_id=%s",
                sp.id, sp.class_unit.name if sp.class_unit else None,
                sp.person_id,
            )
    except Exception as e:
        logger.warning(
            "get_student_profiles не удался (используем базовые данные): %s", e
        )

    return [child]


class MeshAuth:
    """Handles authentication with МЭШ API via OctoDiary."""

    def __init__(self, proxy_url: str = None):
        self.api = AsyncMobileAPI(system=Systems.MES)
        if proxy_url:
            self.api._proxy = proxy_url
        self._proxy_url = proxy_url
        self._pending_sms: Optional[EnterSmsCode] = None

    def _new_api(self) -> AsyncMobileAPI:
        """Создать новый AsyncMobileAPI с сохранением настроек прокси."""
        api = AsyncMobileAPI(system=Systems.MES)
        if self._proxy_url:
            api._proxy = self._proxy_url
        return api

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
                self.api = self._new_api()
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
                self.api = self._new_api()
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
                self.api = self._new_api()
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
        # SOCKS5 прокси для aiohttp-запросов к dnevnik.mos.ru
        if self._proxy_url:
            self.api._socks_proxy = self._proxy_url

        profile_id, mes_role, children = await _finalize_profile_and_children(self.api)

        refresh_token = getattr(self.api, "token_for_refresh", None)
        client_id = getattr(self.api, "client_id", None)
        client_secret = getattr(self.api, "client_secret", None)

        if not refresh_token or not client_id or not client_secret:
            missing = []
            if not refresh_token:
                missing.append("refresh_token")
            if not client_id:
                missing.append("client_id")
            if not client_secret:
                missing.append("client_secret")
            logger.warning(
                "curl_cffi _finalize_auth: НЕПОЛНЫЕ OAuth-данные! "
                "Отсутствуют: [%s]. Обновление токена будет невозможно.",
                ", ".join(missing),
            )

        return {
            "status": "ok",
            "token": token,
            "profile_id": profile_id,
            "mes_role": mes_role,
            "children": children,
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
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
            from config import settings
            proxy_settings = settings.get_proxy_settings()
            if proxy_settings:
                api._socks_proxy = proxy_settings["curl_cffi"]
        except Exception:
            pass

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


# ─── Двухуровневая авторизация: curl_cffi (OctoDiary) → Playwright ──────────
# curl_cffi через SOCKS5 прокси — основной метод (даёт полные OAuth-данные).
# Playwright (браузер) — запасной, если curl_cffi заблокирован по TLS/сети.

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
    """Пробует curl_cffi (OctoDiary) ПЕРВЫМ, при неудаче — откат на Playwright.

    curl_cffi даёт long-lived Bearer-токен + refresh_token + client_id/secret.
    Playwright даёт session-bound токен без OAuth-данных (только как запасной).

    Порядок авторизации:
    1. TCP pre-check (прокси или login.mos.ru напрямую)
    2. TLS pre-check через curl_cffi
    3. curl_cffi (OctoDiary) — основной метод (через SOCKS5 прокси)
    4. Если curl_cffi не смог (сеть) → Playwright fallback
    """

    def __init__(self):
        self._impl = None

    async def start_login(self, login, password, on_retry=None):
        # Читаем прокси из конфига
        proxy_url = None
        try:
            from config import settings
            proxy_settings = settings.get_proxy_settings()
            if proxy_settings:
                proxy_url = proxy_settings["curl_cffi"]
                logger.info("Прокси для авторизации: %s", proxy_settings["url"])
        except Exception:
            pass

        # Шаг 1: TCP pre-check (прокси или login.mos.ru напрямую)
        tcp_ok = await _check_server_reachable(proxy_url)
        if tcp_ok:
            target = "прокси" if proxy_url else f"{_LOGIN_HOST}:{_LOGIN_PORT}"
            logger.info("TCP pre-check %s: OK", target)
        else:
            logger.warning("TCP pre-check: FAIL")
            if proxy_url and ("127.0.0.1" in proxy_url or "localhost" in proxy_url):
                raise NetworkError(
                    "SSH-туннель не готов (локальный прокси-порт не отвечает). "
                    "Проверьте SSH-подключение или перезапустите бота."
                )
            target = "Прокси-сервер" if proxy_url else f"Сервер {_LOGIN_HOST}"
            raise NetworkError(
                f"{target} недоступен (нет TCP-соединения). "
                "Попробуйте позже."
            )

        # Шаг 2: TLS pre-check через curl_cffi
        tls_ok = await _check_curl_cffi_tls(proxy_url)

        # Шаг 3: curl_cffi (OctoDiary) — основной метод
        # Даёт long-lived Bearer-токен + refresh_token + client_id/secret
        if tls_ok:
            try:
                logger.info("Авторизация через curl_cffi (OctoDiary) — основной метод")
                self._impl = _CurlCffiMeshAuth(proxy_url=proxy_url)
                return await self._impl.start_login(login, password, on_retry)
            except AuthenticationError:
                # Неверный пароль — Playwright не поможет
                raise
            except Exception as e:
                logger.warning(
                    "curl_cffi авторизация не удалась, пробуем Playwright: %s", e
                )
        else:
            logger.warning("curl_cffi TLS pre-check: FAIL, переходим к Playwright")

        # Шаг 4: Playwright fallback (браузерная авторизация)
        if _has_playwright:
            try:
                logger.info("Переключаемся на Playwright (браузерная авторизация)")
                self._impl = PlaywrightMeshAuth()
                return await self._impl.start_login(login, password, on_retry)
            except Exception as e:
                logger.error("Playwright тоже не смог: %s", e)
                raise

        # Ни один метод не сработал
        msg = "Сервер login.mos.ru блокирует подключение."
        if not proxy_url:
            msg += (
                " Попробуйте настроить прокси: добавьте MESH_PROXY_URL в .env файл"
                " (например: MESH_PROXY_URL=socks5://host:port)."
            )
        else:
            msg += " Попробуйте другой прокси или подождите."
        raise NetworkError(msg)

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
