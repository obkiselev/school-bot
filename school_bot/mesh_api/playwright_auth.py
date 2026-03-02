"""Browser-based МЭШ authentication via Playwright (Chromium).

Обходит всё: TLS-фингерпринтинг, IP-блокировки, HTTP-детекцию.
Запускает реальный Chromium только на время регистрации (start_login + verify_sms).
После авторизации браузер закрывается; refresh_token работает без браузера.
"""
import asyncio
import logging
import os
import random
import re
from typing import Optional, Dict, Any, Callable, Awaitable

from .exceptions import AuthenticationError, NetworkError

logger = logging.getLogger(__name__)

# ─── URL и пути ────────────────────────────────────────────────────────────────
_MESH_ENTRY_URL = "https://school.mos.ru"          # редиректит на login.mos.ru + OAuth
_OAUTH_REGISTER_PATH = "/sps/oauth/register"       # шаг 1: client_id, client_secret
_OAUTH_TOKEN_PATH = "/sps/oauth/te"                # шаг 7: mos_access_token, refresh_token
_MESH_AUTH_PATH = "/v3/auth/sudir/auth"            # шаг 8: mesh_access_token (school.mos.ru)
_MESH_AUTH_URL = "https://school.mos.ru/v3/auth/sudir/auth"
_OAUTH_CALLBACK_PATH = "/v3/auth/sudir/callback"  # OAuth callback: code → token exchange
_TOKEN_REFRESH_PATH = "/v2/token/refresh"          # новый эндпоинт: mesh_token (201)

# ─── Таймауты (мс для Playwright, сек для asyncio) ────────────────────────────
_BROWSER_LAUNCH_TIMEOUT = 30_000    # запуск Chromium
_PAGE_LOAD_TIMEOUT = 60_000         # goto — networkidle (React SPA нужно время)
_NAVIGATION_TIMEOUT = 90_000        # навигация / ожидание элементов по умолчанию
_LOGIN_URL_WAIT_TIMEOUT = 30_000    # ожидание редиректа с school.mos.ru на login.mos.ru
_INPUT_WAIT_TIMEOUT = 30_000        # ожидание поля ввода (было 20s)
_TOKEN_WAIT_TIMEOUT = 30.0          # сек — ожидание перехвата токена после SMS

# ─── Ключевые слова: mos.ru обнаружил автоматизацию ──────────────────────────
_SUSPICIOUS_KEYWORDS = [
    "подозрительная активность",
    "подозрительную активность",
    "suspicious activity",
    "пароль сброшен",
    "пароль был сброшен",
    "password has been reset",
    "вход в сервис не осуществлен",
    "временно ограничен",
]

# ─── Debug-скриншоты ──────────────────────────────────────────────────────────
_DEBUG_DIR = "data"


class PlaywrightMeshAuth:
    """Авторизация МЭШ через настоящий Chromium (Playwright).

    Публичный интерфейс идентичен MeshAuth:
      start_login(login, password, on_retry=None) -> dict
      verify_sms(code) -> dict
      do_refresh_token(refresh_token, client_id, client_secret) -> dict  [static]
    """

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

        # Данные из перехваченных сетевых ответов
        self._client_id: Optional[str] = None
        self._client_secret: Optional[str] = None
        self._mos_access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._mesh_token: Optional[str] = None
        self._web_token: Optional[str] = None  # токен из /v2/token/refresh (веб-сессионный)

        # Future: сигнал что /sps/oauth/te перехвачен (можно завершать auth)
        self._auth_complete: Optional[asyncio.Future] = None

    # ─────────────────────────────────────────────────────────────────────────
    # Публичный интерфейс
    # ─────────────────────────────────────────────────────────────────────────

    async def start_login(
        self,
        login: str,
        password: str,
        on_retry: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Открывает браузер, логинится на mos.ru, ждёт SMS-шаг.

        Returns:
            {"status": "sms_required", "contact": "7***99", "ttl": 300}
            или {"status": "ok", ...} если вход прошёл без SMS (редко).

        Raises:
            AuthenticationError: Неверные учётные данные.
            NetworkError: Проблема сети или браузера.
        """
        try:
            await self._launch_browser()
            self._auth_complete = asyncio.get_running_loop().create_future()
            self._page.on("response", self._on_response)

            # school.mos.ru — React SPA с кнопкой МЭШID для входа.
            # Загружаем страницу, кликаем кнопку, ждём редирект на login.mos.ru.
            logger.info("Playwright: открываем %s", _MESH_ENTRY_URL)
            try:
                await self._page.goto(
                    _MESH_ENTRY_URL,
                    wait_until="networkidle",
                    timeout=_PAGE_LOAD_TIMEOUT,
                )
            except Exception as e:
                err_str = str(e)
                # Определяем тип ошибки для диагностики
                if "ERR_NAME_NOT_RESOLVED" in err_str:
                    logger.warning("Playwright: goto ОШИБКА DNS: %s", e)
                elif "ERR_TIMED_OUT" in err_str or "Timeout" in err_str:
                    logger.warning("Playwright: goto ТАЙМАУТ: %s", e)
                elif "ERR_CONNECTION" in err_str:
                    logger.warning("Playwright: goto ОШИБКА СОЕДИНЕНИЯ: %s", e)
                else:
                    logger.warning("Playwright: goto ОШИБКА: %s", e)

            logger.info("Playwright: URL после goto: %s", self._page.url)

            # Если уже на login.mos.ru — пропускаем клик
            if "login.mos.ru" not in self._page.url:
                # Кликаем кнопку МЭШID для перехода на login.mos.ru
                await self._click_meshid_button()

                # Ждём появления URL login.mos.ru (без ожидания полной загрузки)
                await self._wait_for_login_page()

            await self._screenshot("1_loaded")

            # ─── Ввод логина ────────────────────────────────────────────────
            login_input = await self._find_input(
                [
                    "input[name='login']",
                    "input[id*='login' i]",
                    "input[placeholder*='логин' i]",
                    "input[placeholder*='Login' i]",
                    "input[type='text']:visible",
                ],
                timeout=_INPUT_WAIT_TIMEOUT,
            )
            if not login_input:
                await self._screenshot("1_no_login_field")
                raise NetworkError(
                    "Страница входа МЭШ не загрузилась. "
                    "Возможно, сервер временно недоступен."
                )

            # Скролл и движение мыши перед вводом (имитация чтения страницы)
            try:
                await self._page.mouse.wheel(0, random.randint(50, 150))
                await asyncio.sleep(random.uniform(0.3, 0.7))
            except Exception:
                pass
            await self._random_mouse_move()
            await self._human_type(login_input, login)
            logger.debug("Playwright: логин введён")

            # ─── Ввод пароля ────────────────────────────────────────────────
            # login.mos.ru показывает логин и пароль на одной странице.
            # Сначала проверяем — пароль уже на странице? Если нет — submit
            # и ждём появления поля пароля (старый flow).
            pwd_input = await self._find_input(
                ["input[type='password']", "input[name='password']"],
                timeout=3_000,  # быстрая проверка: уже на странице?
            )
            if not pwd_input:
                # Поле пароля не видно — нажимаем submit (старый flow)
                await self._click_submit()
                await self._screenshot("2_after_login")
                pwd_input = await self._find_input(
                    ["input[type='password']", "input[name='password']"],
                    timeout=_INPUT_WAIT_TIMEOUT,
                )
                if not pwd_input:
                    await self._check_for_auth_error()
                    await self._screenshot("2_no_password")
                    raise NetworkError(
                        "Поле пароля не появилось. "
                        "Проверьте правильность логина."
                    )

            await self._random_mouse_move()
            await self._human_type(pwd_input, password)
            logger.debug("Playwright: пароль введён")
            await self._click_submit()
            await self._screenshot("3_after_password")

            # Случайная пауза, потом проверяем ошибку
            await self._human_delay(1.5, 3.0)
            await self._check_for_auth_error()

            # ─── SMS-шаг или прямой вход ─────────────────────────────────────
            # Гонка: ждём либо SMS-поле, либо получение токена (вход без SMS)
            sms_selectors = ", ".join([
                "input[autocomplete='one-time-code']",
                "input[name='code']",
                "input[name='smsCode']",
                "input[placeholder*='код' i]",
                "input[placeholder*='code' i]",
            ])

            async def _wait_sms():
                try:
                    return await self._page.wait_for_selector(
                        sms_selectors, state="visible", timeout=_INPUT_WAIT_TIMEOUT
                    )
                except Exception:
                    return None

            async def _wait_token():
                try:
                    await asyncio.wait_for(self._auth_complete, timeout=_INPUT_WAIT_TIMEOUT / 1000)
                    return True
                except asyncio.TimeoutError:
                    return None

            sms_task = asyncio.create_task(_wait_sms())
            token_task = asyncio.create_task(_wait_token())

            done, pending = await asyncio.wait(
                [sms_task, token_task], return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()

            sms_input = sms_task.result() if sms_task in done else None
            token_ready = token_task.result() if token_task in done else None

            if token_ready and not sms_input:
                # Вход прошёл без SMS — авторизация успешна (токен в cookies)
                logger.info("Playwright: вход без SMS — авторизация пройдена, извлекаем токен")
                result = await self._finalize_auth()
                await self._close_browser()
                return result

            if not sms_input:
                # Ни SMS, ни токен — проверяем токены на всякий случай
                if self._mos_access_token or self._mesh_token:
                    logger.info("Playwright: вход без SMS — токен получен (поздно)")
                    result = await self._finalize_auth()
                    await self._close_browser()
                    return result

                # Fallback: проверяем URL — может, браузер уже на school.mos.ru
                current_url = self._page.url
                logger.info("Playwright: URL после ожидания: %s", current_url)

                if "school.mos.ru" in current_url and "login.mos.ru" not in current_url:
                    logger.warning(
                        "Playwright: браузер на school.mos.ru, но токен не перехвачен. "
                        "Извлекаем токен из браузера..."
                    )
                    await self._screenshot("3_url_success_no_token")
                    try:
                        extracted = await self._extract_token_from_browser()
                        if extracted:
                            logger.info("Playwright: токен извлечён из браузера!")
                            result = await self._finalize_auth()
                            await self._close_browser()
                            return result
                    except (NetworkError, AuthenticationError):
                        raise  # пробрасываем реальную ошибку (таймаут, профиль не найден)
                    except Exception as e:
                        logger.warning(
                            "Playwright: не удалось извлечь токен: %s", e
                        )

                await self._screenshot("3_no_sms_field")
                raise NetworkError(
                    "Шаг SMS не появился и токен не получен. "
                    "Возможно, страница входа изменилась (см. data/debug_playwright_*.png)."
                )

            await self._screenshot("4_sms_step")
            contact = await self._extract_phone_contact()
            logger.info("Playwright: SMS-шаг готов, контакт: %s", contact)

            return {"status": "sms_required", "contact": contact, "ttl": 300}

        except (AuthenticationError, NetworkError):
            await self._close_browser()
            raise
        except Exception as e:
            await self._close_browser()
            logger.error("Playwright start_login: неожиданная ошибка: %s", e, exc_info=True)
            raise NetworkError(f"Ошибка браузерной авторизации: {e}")

    async def verify_sms(self, code: str) -> Dict[str, Any]:
        """Вводит SMS-код в открытую страницу браузера и завершает авторизацию.

        Returns:
            {"status": "ok", "token": ..., "refresh_token": ..., ...}

        Raises:
            AuthenticationError: Неверный или истёкший код.
            NetworkError: Таймаут или ошибка сети.
        """
        if not self._page:
            raise AuthenticationError(
                "Сессия браузера истекла. Начните регистрацию заново: /start"
            )

        try:
            sms_input = await self._find_input(
                [
                    "input[autocomplete='one-time-code']",
                    "input[name='code']",
                    "input[name='smsCode']",
                    "input[placeholder*='код' i]",
                    "input[placeholder*='code' i]",
                ],
                timeout=5_000,
            )
            if not sms_input:
                raise NetworkError(
                    "Поле SMS-кода исчезло. Начните регистрацию заново: /start"
                )

            await self._random_mouse_move()
            await self._human_type(sms_input, code)
            await self._click_submit()
            await self._human_delay(1.5, 3.0)
            await self._screenshot("5_after_sms")

            # Проверяем ошибку неверного кода
            await self._check_for_sms_error()

            # Ждём перехват /sps/oauth/te
            try:
                await asyncio.wait_for(self._auth_complete, timeout=_TOKEN_WAIT_TIMEOUT)
            except asyncio.TimeoutError:
                # Fallback: проверяем URL — может, авторизация прошла
                current_url = self._page.url
                logger.info("Playwright: URL после SMS: %s", current_url)

                if "school.mos.ru" in current_url and "login.mos.ru" not in current_url:
                    logger.warning(
                        "Playwright: post-SMS — браузер на school.mos.ru, "
                        "извлекаем токен..."
                    )
                    try:
                        extracted = await self._extract_token_from_browser()
                        if extracted:
                            logger.info("Playwright: post-SMS — токен извлечён!")
                            return await self._finalize_auth()
                    except Exception as e:
                        logger.warning(
                            "Playwright: post-SMS — извлечение: %s", e
                        )

                await self._screenshot("5_token_timeout")
                raise NetworkError(
                    "Сервер МЭШ не вернул токен после ввода кода. "
                    "Попробуйте ввести тот же код ещё раз."
                )

            return await self._finalize_auth()

        except (AuthenticationError, NetworkError):
            raise
        except Exception as e:
            logger.error("Playwright verify_sms: неожиданная ошибка: %s", e, exc_info=True)
            raise NetworkError(f"Ошибка при верификации SMS: {e}")
        finally:
            await self._close_browser()

    @staticmethod
    async def do_refresh_token(
        refresh_token: str,
        client_id: str,
        client_secret: str,
    ) -> Dict[str, Any]:
        """Обновляет токен без браузера — через OctoDiary (без изменений).

        Returns:
            {"token": str, "refresh_token": str | None}

        Raises:
            AuthenticationError: Если refresh_token истёк.
        """
        from octodiary.apis.async_ import AsyncMobileAPI
        from octodiary.urls import Systems

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

    # ─────────────────────────────────────────────────────────────────────────
    # Перехват сетевых ответов
    # ─────────────────────────────────────────────────────────────────────────

    async def _on_response(self, response) -> None:
        """Перехватывает ответы браузера и сохраняет токены."""
        url = response.url

        # Логируем все auth-related ответы для диагностики
        _AUTH_KEYWORDS = ("oauth", "token", "auth", "sudir", "sps")
        url_lower = url.lower()
        if any(kw in url_lower for kw in _AUTH_KEYWORDS):
            logger.info(
                "Playwright: [auth-response] %s %s",
                response.status, url[:200],
            )

        try:
            if response.status >= 400:
                return

            # 3xx — логируем редирект, но не парсим JSON
            if response.status >= 300:
                location = response.headers.get("location", "")
                if location:
                    logger.info(
                        "Playwright: [redirect] %s → %s",
                        url[:100], location[:200],
                    )
                return

            # Шаг 1: регистрация OAuth → client_id, client_secret
            if _OAUTH_REGISTER_PATH in url:
                body = await response.json()
                self._client_id = body.get("client_id")
                self._client_secret = body.get("client_secret")
                logger.info(
                    "Playwright: /register перехвачен, client_id=%s",
                    self._client_id,
                )

            # Шаг 7: обмен кода на токены → mos_access_token, refresh_token
            elif _OAUTH_TOKEN_PATH in url:
                body = await response.json()
                self._mos_access_token = body.get("access_token")
                self._refresh_token = body.get("refresh_token")
                logger.info(
                    "Playwright: /te перехвачен, mos_token=%s...",
                    (self._mos_access_token or "")[:20],
                )
                # Сигналим — можно завершать авторизацию
                if self._auth_complete and not self._auth_complete.done():
                    self._auth_complete.set_result(True)

            # Шаг 8 (бонус): обмен mos→mesh токена браузером
            elif _MESH_AUTH_PATH in url:
                body = await response.json()
                inner = body.get("user_authentication_for_mobile_response", {})
                self._mesh_token = (
                    inner.get("mesh_access_token")
                    or body.get("mesh_access_token")
                    or body.get("token")
                )
                if self._mesh_token:
                    logger.info(
                        "Playwright: /sudir/auth перехвачен, mesh_token=%s...",
                        self._mesh_token[:20],
                    )

            # OAuth callback — сигнализируем что авторизация прошла
            # (token exchange происходит server-side, браузер не видит /sps/oauth/te)
            elif _OAUTH_CALLBACK_PATH in url:
                logger.info("Playwright: OAuth callback перехвачен: %s", url[:200])
                # Даём браузеру секунду на установку cookies, потом сигналим
                if self._auth_complete and not self._auth_complete.done():
                    self._auth_complete.set_result(True)
                    logger.info("Playwright: _auth_complete установлен (callback 200)")

            # Новый эндпоинт: /v2/token/refresh (201) — mesh_token
            elif _TOKEN_REFRESH_PATH in url:
                # Тело может быть пустым, plain-text токеном или JSON
                raw_text = await response.text()
                logger.info(
                    "Playwright: /v2/token/refresh перехвачен (status=%d, body_len=%d)",
                    response.status, len(raw_text),
                )
                token = None
                if raw_text.strip():
                    if raw_text.strip().startswith("{"):
                        # JSON-ответ
                        import json
                        try:
                            body = json.loads(raw_text)
                            logger.info(
                                "Playwright: /v2/token/refresh JSON keys=%s",
                                list(body.keys()),
                            )
                            token = (
                                body.get("mesh_access_token")
                                or body.get("access_token")
                                or body.get("token")
                            )
                        except (json.JSONDecodeError, ValueError) as je:
                            logger.warning(
                                "Playwright: /v2/token/refresh JSON parse: %s", je,
                            )
                    else:
                        # Plain-text ответ — может быть сам токен
                        candidate = raw_text.strip().strip('"')
                        if len(candidate) > 20:
                            token = candidate
                            logger.info(
                                "Playwright: /v2/token/refresh plain-text token: %s...",
                                token[:20],
                            )
                if token:
                    # /v2/token/refresh даёт веб-сессионный токен — он может НЕ работать
                    # для мобильного API (get_events). Сохраняем отдельно.
                    self._web_token = token
                    logger.info(
                        "Playwright: web_token из /v2/token/refresh: %s...",
                        self._web_token[:20],
                    )
                    if self._auth_complete and not self._auth_complete.done():
                        self._auth_complete.set_result(True)

        except Exception as e:
            is_critical = _OAUTH_REGISTER_PATH in url or _OAUTH_TOKEN_PATH in url
            if is_critical:
                logger.error(
                    "Playwright: _on_response КРИТИЧЕСКАЯ ОШИБКА %s: %s "
                    "[OAuth-данные могут быть потеряны!]",
                    url[:200], e, exc_info=True,
                )
            else:
                logger.warning("Playwright: _on_response ошибка %s: %s", url[:200], e)

    # ─────────────────────────────────────────────────────────────────────────
    # Финализация авторизации
    # ─────────────────────────────────────────────────────────────────────────

    async def _finalize_auth(self) -> Dict[str, Any]:
        """Получает mesh_token (если нет — через httpx), затем профиль через OctoDiary."""
        # Если mesh_token не перехвачен браузером — запрашиваем сами
        if not self._mesh_token:
            if self._mos_access_token:
                logger.debug("Playwright: mesh_token не перехвачен, запрашиваем через aiohttp")
                self._mesh_token = await self._fetch_mesh_token(self._mos_access_token)

        # Если mesh_token всё ещё нет — извлекаем из cookies/localStorage браузера
        # Cookie aupd_token устанавливается school.mos.ru при OAuth callback
        # и является рабочим mesh_access_token для API
        if not self._mesh_token and self._page and self._context:
            logger.info(
                "Playwright: mesh_token нет — ждём 2с и извлекаем из cookies браузера..."
            )
            # Даём школьному порталу время установить cookies после OAuth callback
            await asyncio.sleep(2)
            try:
                await self._extract_token_from_browser()
            except Exception as e:
                logger.warning("Playwright: _extract_token_from_browser failed: %s", e)

        # Последний fallback: используем web_token (может не работать для get_events)
        if not self._mesh_token and self._web_token:
            logger.warning(
                "Playwright: используем web_token как fallback "
                "(может не работать для eventcalendar API)"
            )
            self._mesh_token = self._web_token

        if not self._mesh_token:
            raise NetworkError(
                "Не удалось получить токен МЭШ. "
                "Попробуйте перерегистрироваться: /start"
            )

        # Профиль и дети через OctoDiary (с прокси для dnevnik.mos.ru)
        from octodiary.apis.async_ import AsyncMobileAPI
        from octodiary.urls import Systems

        api = AsyncMobileAPI(system=Systems.MES)
        api.token = self._mesh_token

        # SOCKS5 прокси для API-вызовов (dnevnik.mos.ru не доступен напрямую)
        try:
            from config import settings
            proxy_settings = settings.get_proxy_settings()
            if proxy_settings:
                api._socks_proxy = proxy_settings["curl_cffi"]
        except Exception:
            pass

        try:
            profiles = await api.get_users_profile_info()
        except Exception as e:
            logger.error("Playwright: get_users_profile_info: %s", e)
            raise NetworkError(f"Ошибка получения профиля МЭШ: {e}")

        if not profiles:
            raise AuthenticationError("Профиль МЭШ не найден")

        profile_id = profiles[0].id
        mes_role = profiles[0].type

        try:
            family = await api.get_family_profile(profile_id=profile_id)
        except Exception as e:
            logger.error("Playwright: get_family_profile: %s", e)
            raise NetworkError(f"Ошибка получения семейного профиля: {e}")

        if not self._refresh_token or not self._client_id or not self._client_secret:
            missing = []
            if not self._refresh_token:
                missing.append("refresh_token")
            if not self._client_id:
                missing.append("client_id")
            if not self._client_secret:
                missing.append("client_secret")
            logger.warning(
                "Playwright: _finalize_auth возвращает НЕПОЛНЫЕ OAuth-данные! "
                "Отсутствуют: [%s]. Обновление токена будет невозможно.",
                ", ".join(missing),
            )

        return {
            "status": "ok",
            "token": self._mesh_token,
            "profile_id": profile_id,
            "mes_role": mes_role,
            "children": family.children or [],
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

    async def _fetch_mesh_token(self, mos_access_token: str) -> str:
        """POST school.mos.ru/v3/auth/sudir/auth → mesh_access_token."""
        import aiohttp

        headers = {
            "Authorization": f"Bearer {mos_access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    _MESH_AUTH_URL,
                    headers=headers,
                    json={},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status not in (200, 201):
                        text = await resp.text()
                        logger.error(
                            "Playwright: /sudir/auth HTTP %d: %s", resp.status, text[:200]
                        )
                        raise NetworkError(
                            f"Сервер МЭШ вернул ошибку {resp.status}. Попробуйте позже."
                        )
                    data = await resp.json(content_type=None)

            logger.debug("Playwright: /sudir/auth response keys: %s", list(data.keys()))

            inner = data.get("user_authentication_for_mobile_response", {})
            token = (
                inner.get("mesh_access_token")
                or data.get("mesh_access_token")
                or data.get("token")
                or data.get("access_token")
            )
            if not token:
                logger.error(
                    "Playwright: неизвестный формат /sudir/auth: %s", list(data.keys())
                )
                raise NetworkError(
                    f"Неизвестный формат ответа школьного сервера. "
                    f"Поля в ответе: {list(data.keys())}"
                )
            return token

        except NetworkError:
            raise
        except Exception as e:
            logger.error("Playwright: _fetch_mesh_token: %s: %s", type(e).__name__, e)
            raise NetworkError(f"Ошибка обмена токена МЭШ: {type(e).__name__}: {e}")

    async def _extract_token_from_browser(self) -> bool:
        """Извлекает токены из браузера когда _on_response не перехватил их.

        Вызывается как fallback когда браузер уже на school.mos.ru
        (авторизация прошла), но токены не были перехвачены.

        Returns:
            True если хотя бы один токен найден.
        """
        found = False

        # --- A: Cookies ---
        try:
            cookies = await self._context.cookies()
            auth_cookies = [
                c for c in cookies
                if any(kw in c["name"].lower()
                       for kw in ("token", "auth", "session", "aupd", "guid"))
            ]
            logger.info(
                "Playwright: [extract] cookies (%d шт), auth-related: %s",
                len(cookies),
                [c["name"] for c in auth_cookies],
            )
            for cookie in cookies:
                name_lower = cookie["name"].lower()
                value = cookie.get("value", "")
                if not value or len(value) < 10:
                    continue
                if "access_token" in name_lower:
                    if not self._mos_access_token:
                        self._mos_access_token = value
                        logger.info(
                            "Playwright: [extract] mos_access_token из cookie '%s'",
                            cookie["name"],
                        )
                        found = True
                if "mesh" in name_lower and "token" in name_lower:
                    if not self._mesh_token:
                        self._mesh_token = value
                        logger.info(
                            "Playwright: [extract] mesh_token из cookie '%s'",
                            cookie["name"],
                        )
                        found = True
                # aupd_token — school.mos.ru использует для API-авторизации
                # Предпочитаем aupd_token из cookies над web_token из /v2/token/refresh
                if name_lower == "aupd_token":
                    if not self._mesh_token or self._mesh_token == self._web_token:
                        self._mesh_token = value
                        logger.info(
                            "Playwright: [extract] mesh_token из cookie 'aupd_token'",
                        )
                        found = True
        except Exception as e:
            logger.warning("Playwright: [extract] ошибка cookies: %s", e)

        # --- B: localStorage ---
        try:
            ls_tokens = await self._page.evaluate("""() => {
                const r = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const k = localStorage.key(i);
                    if (/token|auth|mesh|access/i.test(k))
                        r[k] = localStorage.getItem(k);
                }
                return r;
            }""")
            if ls_tokens:
                logger.info(
                    "Playwright: [extract] localStorage keys: %s",
                    list(ls_tokens.keys()),
                )
                for key, value in ls_tokens.items():
                    if not value or len(value) < 10:
                        continue
                    kl = key.lower()
                    # school.mos.ru хранит mesh_token как "saved_token"
                    if key == "saved_token" and not self._mesh_token:
                        self._mesh_token = value
                        logger.info("Playwright: [extract] mesh_token из localStorage['saved_token']")
                        found = True
                    elif "mesh" in kl and "token" in kl and not self._mesh_token:
                        self._mesh_token = value
                        logger.info("Playwright: [extract] mesh_token из localStorage['%s']", key)
                        found = True
                    elif "access_token" in kl and not self._mos_access_token:
                        self._mos_access_token = value
                        logger.info("Playwright: [extract] mos_token из localStorage")
                        found = True
        except Exception as e:
            logger.warning("Playwright: [extract] ошибка localStorage: %s", e)

        # --- C: sessionStorage ---
        try:
            ss_tokens = await self._page.evaluate("""() => {
                const r = {};
                for (let i = 0; i < sessionStorage.length; i++) {
                    const k = sessionStorage.key(i);
                    if (/token|auth|mesh|access/i.test(k))
                        r[k] = sessionStorage.getItem(k);
                }
                return r;
            }""")
            if ss_tokens:
                logger.info(
                    "Playwright: [extract] sessionStorage keys: %s",
                    list(ss_tokens.keys()),
                )
                for key, value in ss_tokens.items():
                    if not value or len(value) < 10:
                        continue
                    kl = key.lower()
                    if "mesh" in kl and "token" in kl and not self._mesh_token:
                        self._mesh_token = value
                        logger.info("Playwright: [extract] mesh_token из sessionStorage")
                        found = True
                    elif "access_token" in kl and not self._mos_access_token:
                        self._mos_access_token = value
                        logger.info("Playwright: [extract] mos_token из sessionStorage")
                        found = True
        except Exception as e:
            logger.warning("Playwright: [extract] ошибка sessionStorage: %s", e)

        # --- D: Если есть mos_token — получаем mesh_token через API ---
        if not self._mesh_token and self._mos_access_token:
            logger.info("Playwright: [extract] есть mos_token, запрашиваем mesh_token...")
            try:
                self._mesh_token = await self._fetch_mesh_token(self._mos_access_token)
                found = True
                logger.info("Playwright: [extract] mesh_token получен через API!")
            except Exception as e:
                logger.warning("Playwright: [extract] _fetch_mesh_token: %s", e)

        # --- E: Fetch из браузера (последний шанс) ---
        if not self._mesh_token:
            logger.info("Playwright: [extract] fetch из контекста браузера...")
            try:
                data = await self._page.evaluate("""async () => {
                    try {
                        const r = await fetch('/v3/auth/sudir/auth', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json',
                                      'Accept': 'application/json'},
                            body: '{}',
                            credentials: 'include',
                        });
                        if (!r.ok) return {error: 'HTTP ' + r.status};
                        return await r.json();
                    } catch(e) { return {error: e.message}; }
                }""")
                if data and "error" not in data:
                    logger.info(
                        "Playwright: [extract] browser fetch keys: %s",
                        list(data.keys()),
                    )
                    inner = data.get("user_authentication_for_mobile_response", {})
                    token = (
                        inner.get("mesh_access_token")
                        or data.get("mesh_access_token")
                        or data.get("token")
                        or data.get("access_token")
                    )
                    if token:
                        self._mesh_token = token
                        found = True
                        logger.info("Playwright: [extract] mesh_token из browser fetch!")
                else:
                    logger.warning(
                        "Playwright: [extract] browser fetch: %s",
                        data.get("error", "?") if data else "null",
                    )
            except Exception as e:
                logger.warning("Playwright: [extract] browser fetch: %s", e)

        logger.info(
            "Playwright: [extract] итог: mos=%s mesh=%s",
            "YES" if self._mos_access_token else "NO",
            "YES" if self._mesh_token else "NO",
        )
        return found

    # ─────────────────────────────────────────────────────────────────────────
    # Вспомогательные методы (UI)
    # ─────────────────────────────────────────────────────────────────────────

    async def _human_type(self, element, text: str) -> None:
        """Печатает текст посимвольно с человеческими задержками."""
        await element.click()
        await asyncio.sleep(random.uniform(0.1, 0.3))
        for char in text:
            await element.type(char, delay=random.randint(50, 150))
            if random.random() < 0.1:
                await asyncio.sleep(random.uniform(0.2, 0.5))

    async def _human_delay(self, min_s: float = 0.8, max_s: float = 2.5) -> None:
        """Случайная пауза вместо фиксированной."""
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def _random_mouse_move(self) -> None:
        """Перемещает мышь в случайную точку на странице."""
        try:
            x = random.randint(100, 900)
            y = random.randint(100, 600)
            await self._page.mouse.move(x, y, steps=random.randint(5, 15))
            await asyncio.sleep(random.uniform(0.1, 0.3))
        except Exception:
            pass

    async def _wait_for_login_page(self) -> None:
        """Ждёт пока URL изменится на login.mos.ru (без ожидания load)."""
        deadline = asyncio.get_event_loop().time() + _LOGIN_URL_WAIT_TIMEOUT / 1000
        while asyncio.get_event_loop().time() < deadline:
            if "login.mos.ru" in self._page.url:
                logger.info(
                    "Playwright: редирект на login.mos.ru: %s", self._page.url,
                )
                return
            await asyncio.sleep(0.5)
        logger.warning(
            "Playwright: login.mos.ru не появился за %ds, URL: %s",
            _LOGIN_URL_WAIT_TIMEOUT // 1000, self._page.url,
        )

    async def _click_meshid_button(self) -> None:
        """Нажимает кнопку МЭШID на главной странице school.mos.ru."""
        # Кнопка — это <div class="style_btn__..."> с текстом "МЭШID"
        btn_selectors = [
            "div[class*='btn']",           # основной CSS-класс кнопки
            "button:has-text('МЭШID')",
            "a:has-text('МЭШID')",
        ]
        for selector in btn_selectors:
            try:
                el = await self._page.query_selector(selector)
                if el and await el.is_visible():
                    await self._random_mouse_move()
                    await asyncio.sleep(random.uniform(0.3, 0.8))
                    await el.click()
                    logger.info("Playwright: кнопка МЭШID нажата (%s)", selector)
                    return
            except Exception:
                continue

        # Fallback: ищем любой элемент с текстом "МЭШID" через locator
        try:
            loc = self._page.get_by_text("МЭШID", exact=True).first
            if await loc.count() > 0:
                await loc.click()
                logger.info("Playwright: кнопка МЭШID нажата (text locator)")
                return
        except Exception:
            pass

        logger.warning("Playwright: кнопка МЭШID не найдена")
        await self._screenshot("1_no_meshid_button")

    async def _find_input(self, selectors: list, timeout: int = _INPUT_WAIT_TIMEOUT):
        """Ищет первый видимый input из списка селекторов. Возвращает элемент или None."""
        combined = ", ".join(selectors)
        try:
            return await self._page.wait_for_selector(
                combined, state="visible", timeout=timeout
            )
        except Exception:
            return None

    async def _click_submit(self) -> None:
        """Нажимает кнопку submit текущей формы."""
        candidates = [
            "button[type='submit']",
            "button.btn-primary",
            "button.login-btn",
            "input[type='submit']",
            "button:has-text('Далее')",
            "button:has-text('Войти')",
            "button:has-text('Подтвердить')",
            "button:has-text('Продолжить')",
        ]
        for selector in candidates:
            try:
                el = await self._page.query_selector(selector)
                if el and await el.is_visible():
                    await self._random_mouse_move()
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                    await el.click()
                    return
            except Exception:
                continue
        # Fallback
        logger.debug("Playwright: кнопка submit не найдена, нажимаем Enter")
        await self._page.keyboard.press("Enter")

    async def _check_for_auth_error(self) -> None:
        """Проверяет наличие сообщения об ошибке на странице."""
        _suspicious_msg = (
            "mos.ru обнаружил подозрительную активность и мог сбросить пароль.\n"
            "Пожалуйста:\n"
            "1. Зайдите на mos.ru через обычный браузер\n"
            "2. Восстановите пароль: https://login.mos.ru/sps/recovery\n"
            "3. Подождите 30 минут перед повторной попыткой\n"
            "4. Попробуйте /start заново"
        )

        error_selectors = [
            ".error-message",
            ".alert-danger",
            ".notification-error",
            "[class*='error' i]:not(script):not(style)",
            "[class*='invalid' i]:not(script):not(style)",
        ]
        for selector in error_selectors:
            try:
                el = await self._page.query_selector(selector)
                if not el or not await el.is_visible():
                    continue
                text = (await el.inner_text()).strip()
                if text and 5 < len(text) < 300:
                    if any(kw in text.lower() for kw in _SUSPICIOUS_KEYWORDS):
                        await self._screenshot("error_suspicious_activity")
                        raise AuthenticationError(_suspicious_msg)
                    raise AuthenticationError(f"Ошибка входа: {text}")
            except AuthenticationError:
                raise
            except Exception:
                pass

        # Проверка полного текста страницы на "подозрительную активность"
        try:
            page_text = (await self._page.inner_text("body")).lower()
            if any(kw in page_text for kw in _SUSPICIOUS_KEYWORDS):
                await self._screenshot("error_suspicious_activity")
                raise AuthenticationError(_suspicious_msg)
        except AuthenticationError:
            raise
        except Exception:
            pass

    async def _check_for_sms_error(self) -> None:
        """Проверяет ошибку после ввода SMS-кода."""
        await self._check_for_auth_error()
        try:
            page_text = (await self._page.inner_text("body")).lower()
            if any(
                kw in page_text
                for kw in ("неверный код", "invalid code", "код истёк", "code expired")
            ):
                raise AuthenticationError(
                    "Неверный или истёкший SMS-код. Попробуйте ещё раз."
                )
        except AuthenticationError:
            raise
        except Exception:
            pass

    async def _extract_phone_contact(self) -> str:
        """Извлекает маскированный номер телефона со страницы SMS."""
        try:
            page_text = await self._page.inner_text("body")
            patterns = [
                r"\+?7[\s\-\(]*[\*\d]{3,}[\s\-\)]*\d{2,4}",
                r"\d[\*]{3,}\d{2,4}",
            ]
            for pattern in patterns:
                match = re.search(pattern, page_text)
                if match:
                    return match.group(0).strip()
        except Exception:
            pass
        return "ваш телефон"

    async def _screenshot(self, step: str) -> None:
        """Сохраняет debug-скриншот в data/debug_playwright_<step>.png."""
        if not self._page:
            return
        try:
            os.makedirs(_DEBUG_DIR, exist_ok=True)
            path = os.path.join(_DEBUG_DIR, f"debug_playwright_{step}.png")
            await self._page.screenshot(path=path)
            logger.debug("Playwright: скриншот → %s", path)
        except Exception as e:
            logger.debug("Playwright: скриншот %s не удался: %s", step, e)

    # ─────────────────────────────────────────────────────────────────────────
    # Жизненный цикл браузера
    # ─────────────────────────────────────────────────────────────────────────

    async def _launch_browser(self) -> None:
        """Запускает стелс-Chromium через browser_factory."""
        if self._browser:
            return

        from .browser_factory import create_stealth_browser

        headless = True
        apply_stealth = True
        proxy = None
        try:
            from config import settings
            headless = getattr(settings, "MESH_AUTH_HEADLESS", True)
            apply_stealth = getattr(settings, "MESH_AUTH_STEALTH", True)
            proxy_settings = settings.get_proxy_settings()
            if proxy_settings:
                proxy = proxy_settings["playwright"]
        except Exception:
            pass

        logger.info(
            "Playwright: запускаем стелс-Chromium (headless=%s, stealth=%s, proxy=%s)...",
            headless, apply_stealth, "yes" if proxy else "direct",
        )

        self._playwright, self._browser, self._context, self._page = (
            await create_stealth_browser(
                headless=headless,
                apply_stealth=apply_stealth,
                launch_timeout=_BROWSER_LAUNCH_TIMEOUT,
                navigation_timeout=_NAVIGATION_TIMEOUT,
                proxy=proxy,
            )
        )
        logger.info("Playwright: стелс-браузер запущен")

    async def _close_browser(self) -> None:
        """Закрывает браузер и освобождает ресурсы."""
        for name, attr, method in [
            ("page", "_page", "close"),
            ("context", "_context", "close"),
            ("browser", "_browser", "close"),
            ("playwright", "_playwright", "stop"),
        ]:
            obj = getattr(self, attr, None)
            if obj:
                try:
                    await getattr(obj, method)()
                except Exception:
                    pass
                setattr(self, attr, None)
        logger.debug("Playwright: браузер закрыт")
