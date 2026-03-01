"""Browser factory: запуск стелс-Chromium для авторизации МЭШ.

Пробует patchright (обход CDP-детекции), если нет — стандартный playwright.
Применяет playwright-stealth и ручные JS-скрипты для скрытия автоматизации.
"""
import logging
from typing import Tuple, Any

logger = logging.getLogger(__name__)

# ─── Импорт движка браузера: patchright → playwright ───────────────────────
_USE_PATCHRIGHT = False
_async_playwright = None

try:
    from patchright.async_api import async_playwright as _pw
    _async_playwright = _pw
    _USE_PATCHRIGHT = True
    logger.info("browser_factory: patchright найден (обход CDP-детекции)")
except ImportError:
    try:
        from playwright.async_api import async_playwright as _pw
        _async_playwright = _pw
        logger.info("browser_factory: patchright не найден, используем playwright")
    except ImportError:
        logger.warning("browser_factory: ни patchright, ни playwright не установлены")

# ─── Импорт playwright-stealth ─────────────────────────────────────────────
_HAS_STEALTH = False
try:
    from playwright_stealth import Stealth
    _HAS_STEALTH = True
    logger.info("browser_factory: playwright-stealth найден")
except ImportError:
    logger.info("browser_factory: playwright-stealth не найден, ручные скрипты")

# ─── Актуальный User-Agent (только для стандартного playwright) ─────────────
# patchright сам управляет UA — ему не нужно подменять
_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

# ─── Ручные JS-скрипты антидетекции ───────────────────────────────────────
_STEALTH_SCRIPTS = [
    # navigator.webdriver → undefined
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});",

    # Убрать глобалы Playwright
    "delete window.__playwright__binding__;",
    "delete window.__pwInitScripts;",

    # chrome.runtime (у headless Chrome его нет — это палево)
    """
    if (!window.chrome) { window.chrome = {}; }
    if (!window.chrome.runtime) {
        window.chrome.runtime = {
            connect: function() {},
            sendMessage: function() {},
        };
    }
    """,

    # Permissions API (headless возвращает 'denied' для notifications)
    """
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (params) => (
        params.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : origQuery(params)
    );
    """,

    # Plugins (headless Chrome имеет пустой массив — детектят)
    """
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });
    """,

    # Languages
    """
    Object.defineProperty(navigator, 'languages', {
        get: () => ['ru-RU', 'ru', 'en-US', 'en'],
    });
    """,
]

# ─── Аргументы запуска Chromium ────────────────────────────────────────────
_BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-extensions",
    "--disable-infobars",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-async-dns",       # Использовать системный DNS (не встроенный)
    "--lang=ru-RU,ru",
]


async def create_stealth_browser(
    headless: bool = True,
    apply_stealth: bool = True,
    launch_timeout: int = 30_000,
    navigation_timeout: int = 90_000,
) -> Tuple[Any, Any, Any, Any]:
    """Запускает стелс-Chromium с антидетект-настройками.

    Returns:
        (playwright_instance, browser, context, page)

    Raises:
        RuntimeError: Если ни patchright, ни playwright не установлены.
    """
    if _async_playwright is None:
        raise RuntimeError(
            "Не установлен ни patchright, ни playwright. "
            "Выполните: pip install patchright && patchright install chromium"
        )

    pw = await _async_playwright().start()

    browser = await pw.chromium.launch(
        headless=headless,
        args=_BROWSER_ARGS,
        timeout=launch_timeout,
    )

    # patchright сам управляет User-Agent — НЕ подменяем
    # Для стандартного playwright — ставим актуальный UA
    context_kwargs = {
        "locale": "ru-RU",
        "timezone_id": "Europe/Moscow",
        "viewport": {"width": 1280, "height": 800},
        "extra_http_headers": {
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    }

    if not _USE_PATCHRIGHT:
        context_kwargs["user_agent"] = _CHROME_UA

    context = await browser.new_context(**context_kwargs)
    context.set_default_navigation_timeout(navigation_timeout)

    # Стелс-скрипты ТОЛЬКО для стандартного playwright.
    # patchright обрабатывает стелс на уровне CDP — добавление JS-скриптов
    # поверх patchright конфликтует с его внутренними механизмами и ломает навигацию.
    if apply_stealth and not _USE_PATCHRIGHT:
        # playwright-stealth (библиотека)
        if _HAS_STEALTH:
            try:
                stealth = Stealth(
                    navigator_languages_override=("ru-RU", "ru", "en-US", "en"),
                    init_scripts_only=True,
                )
                await stealth.apply_stealth_async(context)
                logger.debug("browser_factory: playwright-stealth применён")
            except Exception as e:
                logger.warning("browser_factory: playwright-stealth ошибка: %s", e)

        # Ручные JS-скрипты (дополнительный слой)
        for script in _STEALTH_SCRIPTS:
            await context.add_init_script(script)
        logger.debug("browser_factory: ручные стелс-скрипты применены")
    elif _USE_PATCHRIGHT:
        logger.debug("browser_factory: patchright — стелс на уровне CDP, JS-скрипты не нужны")

    page = await context.new_page()

    engine = "patchright" if _USE_PATCHRIGHT else "playwright"
    stealth_info = "stealth" if apply_stealth else "без stealth"
    mode = "headless" if headless else "headed"
    logger.info(
        "browser_factory: браузер запущен (%s, %s, %s, v%s)",
        engine, stealth_info, mode, browser.version,
    )

    return pw, browser, context, page
