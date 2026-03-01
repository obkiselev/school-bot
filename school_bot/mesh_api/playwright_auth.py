"""Browser-based МЭШ authentication via Playwright (Chromium).

Обходит всё: TLS-фингерпринтинг, IP-блокировки, HTTP-детекцию.
Запускает реальный Chromium только на время регистрации (start_login + verify_sms).
После авторизации браузер закрывается; refresh_token работает без браузера.
"""
import asyncio
import logging
import os
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

# ─── Таймауты (мс для Playwright, сек для asyncio) ────────────────────────────
_BROWSER_LAUNCH_TIMEOUT = 30_000    # запуск Chromium
_PAGE_LOAD_TIMEOUT = 60_000         # goto — networkidle (React SPA нужно время)
_NAVIGATION_TIMEOUT = 90_000        # навигация / ожидание элементов по умолчанию
_LOGIN_URL_WAIT_TIMEOUT = 30_000    # ожидание редиректа с school.mos.ru на login.mos.ru
_INPUT_WAIT_TIMEOUT = 30_000        # ожидание поля ввода (было 20s)
_TOKEN_WAIT_TIMEOUT = 30.0          # сек — ожидание перехвата токена после SMS

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
                logger.debug("Playwright: goto: %s (продолжаем)", e)

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

            await login_input.fill(login)
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

            await pwd_input.fill(password)
            logger.debug("Playwright: пароль введён")
            await self._click_submit()
            await self._screenshot("3_after_password")

            # Ждём секунду, потом проверяем ошибку неверного пароля
            await asyncio.sleep(1.5)
            await self._check_for_auth_error()

            # ─── SMS-шаг ────────────────────────────────────────────────────
            sms_input = await self._find_input(
                [
                    "input[autocomplete='one-time-code']",
                    "input[name='code']",
                    "input[name='smsCode']",
                    "input[placeholder*='код' i]",
                    "input[placeholder*='code' i]",
                ],
                timeout=_INPUT_WAIT_TIMEOUT,
            )

            if not sms_input:
                # Вход прошёл без SMS?
                if self._mos_access_token or self._mesh_token:
                    result = await self._finalize_auth()
                    await self._close_browser()
                    return result
                await self._screenshot("3_no_sms_field")
                raise NetworkError(
                    "Шаг SMS не появился. "
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

            await sms_input.fill(code)
            await self._click_submit()
            await asyncio.sleep(1.5)
            await self._screenshot("5_after_sms")

            # Проверяем ошибку неверного кода
            await self._check_for_sms_error()

            # Ждём перехват /sps/oauth/te
            try:
                await asyncio.wait_for(self._auth_complete, timeout=_TOKEN_WAIT_TIMEOUT)
            except asyncio.TimeoutError:
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
        try:
            if response.status != 200:
                return

            # Шаг 1: регистрация OAuth → client_id, client_secret
            if _OAUTH_REGISTER_PATH in url:
                body = await response.json()
                self._client_id = body.get("client_id")
                self._client_secret = body.get("client_secret")
                logger.debug(
                    "Playwright: /register перехвачен, client_id=%s",
                    self._client_id,
                )

            # Шаг 7: обмен кода на токены → mos_access_token, refresh_token
            elif _OAUTH_TOKEN_PATH in url:
                body = await response.json()
                self._mos_access_token = body.get("access_token")
                self._refresh_token = body.get("refresh_token")
                logger.debug(
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
                    logger.debug(
                        "Playwright: /sudir/auth перехвачен, mesh_token=%s...",
                        self._mesh_token[:20],
                    )

        except Exception as e:
            logger.debug("Playwright: _on_response %s: %s", url, e)

    # ─────────────────────────────────────────────────────────────────────────
    # Финализация авторизации
    # ─────────────────────────────────────────────────────────────────────────

    async def _finalize_auth(self) -> Dict[str, Any]:
        """Получает mesh_token (если нет — через httpx), затем профиль через OctoDiary."""
        # Если mesh_token не перехвачен браузером — запрашиваем сами
        if not self._mesh_token:
            if not self._mos_access_token:
                raise NetworkError(
                    "Не удалось получить токен МЭШ. "
                    "Попробуйте перерегистрироваться: /start"
                )
            logger.debug("Playwright: mesh_token не перехвачен, запрашиваем через aiohttp")
            self._mesh_token = await self._fetch_mesh_token(self._mos_access_token)

        # Профиль и дети через OctoDiary
        from octodiary.apis.async_ import AsyncMobileAPI
        from octodiary.urls import Systems

        api = AsyncMobileAPI(system=Systems.MES)
        api.token = self._mesh_token

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
            logger.error("Playwright: _fetch_mesh_token: %s", e)
            raise NetworkError(f"Ошибка обмена токена МЭШ: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Вспомогательные методы (UI)
    # ─────────────────────────────────────────────────────────────────────────

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
                    await el.click()
                    return
            except Exception:
                continue
        # Fallback
        logger.debug("Playwright: кнопка submit не найдена, нажимаем Enter")
        await self._page.keyboard.press("Enter")

    async def _check_for_auth_error(self) -> None:
        """Проверяет наличие сообщения об ошибке на странице."""
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
                    raise AuthenticationError(f"Ошибка входа: {text}")
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
        try:
            from config import settings
            headless = getattr(settings, "MESH_AUTH_HEADLESS", True)
            apply_stealth = getattr(settings, "MESH_AUTH_STEALTH", True)
        except Exception:
            pass

        logger.info(
            "Playwright: запускаем стелс-Chromium (headless=%s, stealth=%s)...",
            headless, apply_stealth,
        )

        self._playwright, self._browser, self._context, self._page = (
            await create_stealth_browser(
                headless=headless,
                apply_stealth=apply_stealth,
                launch_timeout=_BROWSER_LAUNCH_TIMEOUT,
                navigation_timeout=_NAVIGATION_TIMEOUT,
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
