"""Start command handler."""
import asyncio
import ssl as _ssl
import time
import logging
import aiohttp
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from database.crud import user_exists
from states.registration import RegistrationStates

logger = logging.getLogger(__name__)
router = Router()


async def _close_octodiary_session(api) -> None:
    """Закрыть внутреннюю сессию OctoDiary после диагностического теста."""
    try:
        session = getattr(api, "_login_info", {}).get("session")
        if session and not session.closed:
            await session.close()
    except Exception:
        pass


@router.message(Command("testauth"))
async def cmd_test_auth(message: Message):
    """Диагностика соединения с МЭШ — тест изнутри бота."""
    await message.answer("Запускаю диагностику МЭШ соединения...")

    from octodiary.apis.async_ import AsyncMobileAPI
    from octodiary.urls import Systems
    from octodiary.exceptions import APIError

    results = []

    # Тест 1: aiohttp без wait_for
    t = time.time()
    api = AsyncMobileAPI(system=Systems.MES)
    try:
        await api.login("diag_test@test.ru", "WrongPass_Diag1")
        results.append(f"Тест 1: НЕОЖИДАННЫЙ УСПЕХ ({time.time()-t:.2f}с)")
    except aiohttp.ConnectionTimeoutError:
        elapsed = time.time() - t
        results.append(
            f"Тест 1 ({elapsed:.2f}с): OctoDiary connect timeout — "
            f"TCP+TLS не завершился за {elapsed:.0f}с"
        )
    except aiohttp.ClientConnectorError as e:
        elapsed = time.time() - t
        results.append(f"Тест 1 ({elapsed:.2f}с): DNS/connect error — {str(e)[:60]}")
    except asyncio.TimeoutError:
        elapsed = time.time() - t
        results.append(f"Тест 1 ({elapsed:.2f}с): asyncio timeout")
    except APIError as e:
        elapsed = time.time() - t
        results.append(
            f"Тест 1 ({elapsed:.2f}с): APIError — {e.error_types} "
            f"(СЕТЬ РАБОТАЕТ)"
        )
    except Exception as e:
        elapsed = time.time() - t
        results.append(f"Тест 1 ({elapsed:.2f}с): {type(e).__name__}: {str(e)[:60]}")
    finally:
        await _close_octodiary_session(api)

    # Тест 2: aiohttp с wait_for(15с)
    t = time.time()
    api = AsyncMobileAPI(system=Systems.MES)
    try:
        await asyncio.wait_for(
            api.login("diag_test2@test.ru", "WrongPass_Diag2"),
            timeout=15,
        )
        results.append(f"Тест 2: НЕОЖИДАННЫЙ УСПЕХ ({time.time()-t:.2f}с)")
    except aiohttp.ConnectionTimeoutError:
        elapsed = time.time() - t
        results.append(
            f"Тест 2 ({elapsed:.2f}с): OctoDiary connect timeout — "
            f"TCP+TLS не завершился за {elapsed:.0f}с"
        )
    except aiohttp.ClientConnectorError as e:
        elapsed = time.time() - t
        results.append(f"Тест 2 ({elapsed:.2f}с): DNS/connect error — {str(e)[:60]}")
    except asyncio.TimeoutError:
        elapsed = time.time() - t
        results.append(f"Тест 2 ({elapsed:.2f}с): asyncio.wait_for(15с) истёк")
    except APIError as e:
        elapsed = time.time() - t
        results.append(
            f"Тест 2 ({elapsed:.2f}с): APIError — {e.error_types} "
            f"(СЕТЬ РАБОТАЕТ)"
        )
    except Exception as e:
        elapsed = time.time() - t
        results.append(f"Тест 2 ({elapsed:.2f}с): {type(e).__name__}: {str(e)[:60]}")
    finally:
        await _close_octodiary_session(api)

    # Тест 3: чистый TCP (без TLS)
    t = time.time()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("login.mos.ru", 443),
            timeout=5,
        )
        writer.close()
        await writer.wait_closed()
        results.append(f"Тест 3 ({time.time()-t:.2f}с): TCP OK — login.mos.ru:443 доступен")
    except asyncio.TimeoutError:
        results.append(f"Тест 3 ({time.time()-t:.2f}с): TCP TIMEOUT — порт 443 не отвечает")
    except OSError as e:
        results.append(f"Тест 3 ({time.time()-t:.2f}с): TCP ERROR — {str(e)[:60]}")

    # Тест 4: TCP + TLS handshake (Python/OpenSSL)
    t = time.time()
    try:
        ssl_ctx = _ssl.create_default_context()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("login.mos.ru", 443, ssl=ssl_ctx),
            timeout=30,
        )
        writer.close()
        await writer.wait_closed()
        results.append(f"Тест 4 ({time.time()-t:.2f}с): TLS OK — Python/OpenSSL handshake")
    except asyncio.TimeoutError:
        results.append(f"Тест 4 ({time.time()-t:.2f}с): TLS TIMEOUT >30с — OpenSSL заблокирован (JA3)")
    except OSError as e:
        results.append(f"Тест 4 ({time.time()-t:.2f}с): TLS ERROR — {str(e)[:60]}")

    # Тест 5: curl_cffi GET к root login.mos.ru
    t = time.time()
    try:
        from curl_cffi.requests import AsyncSession
        async with AsyncSession(impersonate="chrome124") as s:
            resp = await s.get("https://login.mos.ru/", allow_redirects=False)
        results.append(
            f"Тест 5 ({time.time()-t:.2f}с): curl_cffi OK — HTTP {resp.status_code}"
        )
    except ImportError:
        results.append("Тест 5: curl_cffi не установлен (pip install curl-cffi)")
    except Exception as e:
        elapsed = time.time() - t
        results.append(f"Тест 5 ({elapsed:.2f}с): curl_cffi ERROR — {str(e)[:80]}")

    # Тест 6: curl_cffi POST к /sps/oauth/register (первый реальный шаг OAuth)
    t = time.time()
    try:
        from curl_cffi.requests import AsyncSession
        async with AsyncSession(impersonate="chrome124") as s:
            resp = await s.post(
                "https://login.mos.ru/sps/oauth/register",
                headers={"Authorization": "Bearer FqzGn1dTJ9BQCHgV0rmMjtYFIgaFf9TrGVEzgtju-zbtIbeJSkIyDcl0e2QMirTNpEqovTT8NvOLZI0XklVEIw"},
                json={"software_id": "dnevnik.mos.ru", "device_type": "android_phone"},
            )
        results.append(
            f"Тест 6 ({time.time()-t:.2f}с): OAuth API OK — HTTP {resp.status_code} "
            f"(curl_cffi достигает API МЭШ!)"
        )
    except ImportError:
        results.append("Тест 6: curl_cffi не установлен")
    except Exception as e:
        elapsed = time.time() - t
        results.append(f"Тест 6 ({elapsed:.2f}с): OAuth API ERROR — {str(e)[:80]}")

    report = "\n".join(results)

    # Динамическая расшифровка на основе реальных результатов
    test2_ok = any("СЕТЬ РАБОТАЕТ" in r for r in results)
    test4_timeout = any("Тест 4" in r and "TIMEOUT" in r for r in results)
    test5_ok = any("Тест 5" in r and "OK" in r for r in results)
    test6_ok = any("Тест 6" in r and "OK" in r for r in results)

    hints = ["\n\nРасшифровка:"]
    if test2_ok:
        hints.append("✅ Тест 2 OK — curl_cffi работает, OAuth-шаги 1-3 проходят")
    else:
        hints.append("❌ Тест 2 FAIL — соединение с МЭШ не работает")

    if test4_timeout and test2_ok:
        hints.append("✅ Тест 4 TIMEOUT + Тест 2 OK — JA3 обходится через curl_cffi")
    elif not test4_timeout:
        hints.append("⚠️ Тест 4 OK — Python/OpenSSL не заблокирован (неожиданно)")

    if test6_ok:
        hints.append("✅ Тест 6 OK — прямой POST к OAuth API работает")
    elif test2_ok:
        hints.append("⚠️ Тест 6 ERROR при Тест 2 OK — возможна проблема со software_statement")
    else:
        hints.append("❌ Тест 6 ERROR — curl_cffi не достигает OAuth API")

    if test5_ok:
        hints.append("ℹ️ Тест 5 OK — root login.mos.ru доступен")
    elif test2_ok:
        hints.append("ℹ️ Тест 5 ERROR при Тест 2 OK — root блокирован, но API работает (норма)")
    else:
        hints.append("❌ Тест 5 ERROR — login.mos.ru недоступен даже через curl_cffi")

    if test2_ok and not test6_ok:
        hints.append("\n🔍 Вероятная причина ошибки входа: шаг 4+ OAuth (sms/bind или /sps/oauth/te)")
    elif not test2_ok:
        hints.append("\n🔴 Авторизация невозможна — проверьте сетевое подключение")

    hint = "\n".join(hints)
    logger.info("Auth diagnostic:\n%s", report)
    await message.answer(f"Результаты:\n{report}{hint}")


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """
    Handle /start command.

    If user is registered, show main menu.
    If not, start registration flow.
    """
    user_id = message.from_user.id

    # Check if user already registered
    if await user_exists(user_id):
        await message.answer(
            "👋 С возвращением!\n\n"
            "Доступные команды:\n"
            "/raspisanie - Расписание уроков\n"
            "/ocenki - Оценки\n"
            "/dz - Домашние задания\n"
            "/profile - Мой профиль\n"
            "/settings - Настройки уведомлений\n"
            "/help - Справка"
        )
    else:
        # Start registration
        await message.answer(
            "👋 Добро пожаловать в Школьный помощник!\n\n"
            "Этот бот поможет вам получать информацию о школьной жизни ваших детей:\n"
            "• Расписание уроков\n"
            "• Оценки\n"
            "• Домашние задания\n\n"
            "Для начала работы необходимо войти в систему МЭШ.\n\n"
            "Введите ваш логин от dnevnik.mos.ru:"
        )

        # Set FSM state to wait for login
        await state.set_state(RegistrationStates.waiting_for_mesh_login)
