"""Start command handler."""
import asyncio
import ssl as _ssl
import time
import logging
import aiohttp
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import settings
from database.crud import user_exists, delete_user, get_user_role, get_user, ensure_quiz_user, set_user_access
from states.registration import RegistrationStates
from keyboards.main_menu import parent_menu_keyboard, student_menu_keyboard, admin_menu_keyboard, home_button

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
    """Handle /start — role-based menu."""
    await state.clear()
    user_id = message.from_user.id

    # Проверяем, есть ли пользователь в БД
    if not await user_exists(user_id):
        # Автовосстановление главного админа (мог удалиться при перерегистрации)
        if settings.ADMIN_ID and user_id == settings.ADMIN_ID:
            await set_user_access(user_id, "admin")
            logger.info("Автовосстановление админа user_id=%d", user_id)
        else:
            await message.answer(
                "❗ Доступ ограничен.\n\n"
                "Для получения доступа обратитесь к администратору."
            )
            return

    role = await get_user_role(user_id)

    if role == "admin":
        # Админ — проверяем, есть ли МЭШ-данные (если да — полное меню)
        user = await get_user(user_id)
        has_mesh = user and user.get("mesh_token")
        await message.answer(
            "👋 С возвращением, администратор!\n\n"
            "Доступные команды:\n"
            "/raspisanie — Расписание уроков\n"
            "/test — Пройти тест по языку\n"
            "/allow — Добавить пользователя\n"
            "/block — Заблокировать пользователя\n"
            "/users — Список пользователей\n"
            "/help — Справка",
            reply_markup=admin_menu_keyboard(),
        )

    elif role == "parent":
        # Родитель — проверяем, прошёл ли МЭШ-регистрацию
        user = await get_user(user_id)
        has_mesh = user and user.get("mesh_login")
        if has_mesh:
            await message.answer(
                "👋 С возвращением!\n\n"
                "Выберите действие:",
                reply_markup=parent_menu_keyboard(),
            )
        else:
            # Ещё не прошёл МЭШ-регистрацию
            await message.answer(
                "👋 Добро пожаловать!\n\n"
                "Для доступа к расписанию, оценкам и ДЗ\n"
                "необходимо войти в систему МЭШ.\n\n"
                "Введите ваш логин от dnevnik.mos.ru:"
            )
            await state.set_state(RegistrationStates.waiting_for_mesh_login)

    elif role == "student":
        # Ученик — обновить данные и показать меню тестирования
        await ensure_quiz_user(user_id, message.from_user.username, message.from_user.first_name)
        await message.answer(
            "👋 Привет! Я Школьный помощник.\n\n"
            "Выбери, что хочешь сделать:",
            reply_markup=student_menu_keyboard(),
        )

    else:
        await message.answer("❗ Роль не определена. Обратитесь к администратору.")



@router.callback_query(F.data == "go_home")
async def go_home(callback: CallbackQuery, state: FSMContext):
    """Return to main menu based on role."""
    await state.clear()
    user_id = callback.from_user.id
    role = await get_user_role(user_id)

    if role == "admin":
        await callback.message.edit_text("Главное меню:", reply_markup=admin_menu_keyboard())
    elif role == "parent":
        await callback.message.edit_text("Главное меню:", reply_markup=parent_menu_keyboard())
    elif role == "student":
        await callback.message.edit_text(
            "👋 Выбери, что хочешь сделать:",
            reply_markup=student_menu_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "reregister")
async def cb_reregister(callback: CallbackQuery, state: FSMContext):
    """Перерегистрация: удалить старые данные и начать заново."""
    user_id = callback.from_user.id

    await delete_user(user_id)
    await state.clear()
    logger.info("Перерегистрация: пользователь удалён, user_id=%d", user_id)

    await callback.message.edit_text(
        "Старые данные удалены.\n\n"
        "Введите ваш логин от dnevnik.mos.ru:"
    )
    await state.set_state(RegistrationStates.waiting_for_mesh_login)
    await callback.answer()
