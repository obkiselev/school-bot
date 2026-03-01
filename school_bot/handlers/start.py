"""Start command handler."""
import asyncio
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


@router.message(Command("testauth"))
async def cmd_test_auth(message: Message):
    """Диагностика соединения с МЭШ — тест изнутри бота."""
    await message.answer("Запускаю диагностику МЭШ соединения...")

    from octodiary.apis.async_ import AsyncMobileAPI
    from octodiary.urls import Systems
    from octodiary.exceptions import APIError

    results = []

    # Тест 1: без wait_for — смотрим какая ошибка бросается
    t = time.time()
    try:
        api = AsyncMobileAPI(system=Systems.MES)
        await api.login("diag_test@test.ru", "WrongPass_Diag1")
        results.append(f"Тест 1: НЕОЖИДАННЫЙ УСПЕХ ({time.time()-t:.2f}с)")
    except aiohttp.ConnectionTimeoutError:
        elapsed = time.time() - t
        results.append(
            f"Тест 1 ({elapsed:.2f}с): OctoDiary connect timeout — "
            f"login.mos.ru не ответил на TCP за {elapsed:.0f}с"
        )
    except aiohttp.ClientConnectorError as e:
        elapsed = time.time() - t
        results.append(f"Тест 1 ({elapsed:.2f}с): DNS/connect error — {str(e)[:60]}")
    except asyncio.TimeoutError:
        elapsed = time.time() - t
        results.append(f"Тест 1 ({elapsed:.2f}с): asyncio timeout (внешний)")
    except APIError as e:
        elapsed = time.time() - t
        results.append(
            f"Тест 1 ({elapsed:.2f}с): APIError — {e.error_types} "
            f"(СЕТЬ РАБОТАЕТ, сервер ответил)"
        )
    except Exception as e:
        elapsed = time.time() - t
        results.append(f"Тест 1 ({elapsed:.2f}с): {type(e).__name__}: {str(e)[:60]}")

    # Тест 2: с wait_for(15) — наш внешний таймаут поверх OctoDiary
    t = time.time()
    try:
        api = AsyncMobileAPI(system=Systems.MES)
        await asyncio.wait_for(
            api.login("diag_test2@test.ru", "WrongPass_Diag2"),
            timeout=15,
        )
        results.append(f"Тест 2: НЕОЖИДАННЫЙ УСПЕХ ({time.time()-t:.2f}с)")
    except aiohttp.ConnectionTimeoutError:
        elapsed = time.time() - t
        results.append(
            f"Тест 2 ({elapsed:.2f}с): OctoDiary connect timeout — "
            f"login.mos.ru не ответил на TCP за {elapsed:.0f}с"
        )
    except aiohttp.ClientConnectorError as e:
        elapsed = time.time() - t
        results.append(f"Тест 2 ({elapsed:.2f}с): DNS/connect error — {str(e)[:60]}")
    except asyncio.TimeoutError:
        elapsed = time.time() - t
        results.append(f"Тест 2 ({elapsed:.2f}с): asyncio.wait_for(15с) истёк — сервер очень медленный")
    except APIError as e:
        elapsed = time.time() - t
        results.append(
            f"Тест 2 ({elapsed:.2f}с): APIError — {e.error_types} "
            f"(СЕТЬ РАБОТАЕТ, сервер ответил)"
        )
    except Exception as e:
        elapsed = time.time() - t
        results.append(f"Тест 2 ({elapsed:.2f}с): {type(e).__name__}: {str(e)[:60]}")

    # Тест 3: чистый TCP — обходит aiohttp полностью
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
        results.append(f"Тест 3 ({time.time()-t:.2f}с): TCP TIMEOUT — порт 443 не отвечает за 5с")
    except OSError as e:
        results.append(f"Тест 3 ({time.time()-t:.2f}с): TCP ERROR — {type(e).__name__}: {str(e)[:60]}")

    report = "\n".join(results)
    hint = (
        "\n\nРасшифровка:\n"
        "• Тест 3 = TCP OK + Тест 1/2 = OctoDiary timeout → сервер медленный (таймаут увеличен до 15с)\n"
        "• Тест 3 = TCP TIMEOUT → login.mos.ru недоступен с этого IP\n"
        "• Тест 1/2 = APIError (неверные реквизиты) → всё работает"
    )
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
