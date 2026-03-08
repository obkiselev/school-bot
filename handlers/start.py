"""Start command handler."""
import asyncio
import ssl as _ssl
import time
import logging
import aiohttp
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, BotCommandScopeChat
from aiogram.fsm.context import FSMContext

from config import settings
from database.crud import user_exists, delete_user, get_user_role, get_user, ensure_quiz_user, set_user_access
from states.registration import RegistrationStates
from keyboards.main_menu import full_menu_keyboard, student_menu_keyboard, home_button

logger = logging.getLogger(__name__)
router = Router()


async def _close_octodiary_session(api) -> None:
    """Р—Р°РєСЂС‹С‚СЊ РІРЅСѓС‚СЂРµРЅРЅСЋСЋ СЃРµСЃСЃРёСЋ OctoDiary РїРѕСЃР»Рµ РґРёР°РіРЅРѕСЃС‚РёС‡РµСЃРєРѕРіРѕ С‚РµСЃС‚Р°."""
    try:
        session = getattr(api, "_login_info", {}).get("session")
        if session and not session.closed:
            await session.close()
    except Exception as e:
        logger.debug("Failed to close OctoDiary session: %s", e)


async def _set_user_commands(bot, user_id: int, role: str):
    """Set Telegram Menu commands per user role."""
    if role == "admin":
        commands = [
            BotCommand(command="start", description="Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ"),
            BotCommand(command="raspisanie", description="Р Р°СЃРїРёСЃР°РЅРёРµ СѓСЂРѕРєРѕРІ"),
            BotCommand(command="ocenki", description="РћС†РµРЅРєРё"),
            BotCommand(command="dz", description="Р”РѕРјР°С€РЅРёРµ Р·Р°РґР°РЅРёСЏ"),
            BotCommand(command="test", description="РџСЂРѕР№С‚Рё С‚РµСЃС‚"),
            BotCommand(command="profile", description="РњРѕР№ РїСЂРѕС„РёР»СЊ"),
            BotCommand(command="report", description="PDF отчеты"),
            BotCommand(command="settings", description="РќР°СЃС‚СЂРѕР№РєРё СѓРІРµРґРѕРјР»РµРЅРёР№"),
            BotCommand(command="remind", description="РњРѕРё РЅР°РїРѕРјРёРЅР°РЅРёСЏ"),
            BotCommand(command="import_questions", description="РРјРїРѕСЂС‚ РІРѕРїСЂРѕСЃРѕРІ РёР· JSON"),
            BotCommand(command="allow", description="Р”РѕР±Р°РІРёС‚СЊ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ"),
            BotCommand(command="block", description="Р—Р°Р±Р»РѕРєРёСЂРѕРІР°С‚СЊ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ"),
            BotCommand(command="users", description="РЎРїРёСЃРѕРє РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№"),
            BotCommand(command="health", description="РџСЂРѕРІРµСЂРєР° СЃРѕСЃС‚РѕСЏРЅРёСЏ"),
            BotCommand(command="help", description="РЎРїСЂР°РІРєР°"),
        ]
    elif role == "parent":
        commands = [
            BotCommand(command="start", description="Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ"),
            BotCommand(command="raspisanie", description="Р Р°СЃРїРёСЃР°РЅРёРµ СѓСЂРѕРєРѕРІ"),
            BotCommand(command="ocenki", description="РћС†РµРЅРєРё"),
            BotCommand(command="dz", description="Р”РѕРјР°С€РЅРёРµ Р·Р°РґР°РЅРёСЏ"),
            BotCommand(command="test", description="РџСЂРѕР№С‚Рё С‚РµСЃС‚"),
            BotCommand(command="profile", description="РњРѕР№ РїСЂРѕС„РёР»СЊ"),
            BotCommand(command="report", description="PDF отчеты"),
            BotCommand(command="settings", description="РќР°СЃС‚СЂРѕР№РєРё СѓРІРµРґРѕРјР»РµРЅРёР№"),
            BotCommand(command="remind", description="РњРѕРё РЅР°РїРѕРјРёРЅР°РЅРёСЏ"),
            BotCommand(command="import_questions", description="РРјРїРѕСЂС‚ РІРѕРїСЂРѕСЃРѕРІ РёР· JSON"),
            BotCommand(command="help", description="РЎРїСЂР°РІРєР°"),
        ]
    elif role == "student":
        commands = [
            BotCommand(command="start", description="Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ"),
            BotCommand(command="raspisanie", description="Р Р°СЃРїРёСЃР°РЅРёРµ СѓСЂРѕРєРѕРІ"),
            BotCommand(command="dz", description="Р”РѕРјР°С€РЅРёРµ Р·Р°РґР°РЅРёСЏ"),
            BotCommand(command="test", description="РџСЂРѕР№С‚Рё С‚РµСЃС‚"),
            BotCommand(command="social", description="РЎРѕСЂРµРІРЅРѕРІР°РЅРёСЏ"),
            BotCommand(command="share", description="РћС‚РєСЂС‹С‚СЊ shared-СЂРµР·СѓР»СЊС‚Р°С‚"),
            BotCommand(command="profile", description="РњРѕР№ РїСЂРѕС„РёР»СЊ"),
            BotCommand(command="report", description="PDF отчеты"),
            BotCommand(command="settings", description="РќР°СЃС‚СЂРѕР№РєРё СѓРІРµРґРѕРјР»РµРЅРёР№"),
            BotCommand(command="remind", description="РњРѕРё РЅР°РїРѕРјРёРЅР°РЅРёСЏ"),
            BotCommand(command="help", description="РЎРїСЂР°РІРєР°"),
        ]
    else:
        commands = [
            BotCommand(command="start", description="Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ"),
            BotCommand(command="help", description="РЎРїСЂР°РІРєР°"),
        ]
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=user_id))
    except Exception as e:
        logger.warning("Failed to set commands for user %d: %s", user_id, e)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """РЎРїСЂР°РІРєР° РїРѕ РґРѕСЃС‚СѓРїРЅС‹Рј РєРѕРјР°РЅРґР°Рј."""
    user_id = message.from_user.id
    role = await get_user_role(user_id)

    if not role:
        await message.answer(
            "<b>РЎРїСЂР°РІРєР°</b>\n\n"
            "/start вЂ” РќР°С‡Р°С‚СЊ СЂР°Р±РѕС‚Сѓ СЃ Р±РѕС‚РѕРј\n\n"
            "Р”Р»СЏ РїРѕР»СѓС‡РµРЅРёСЏ РґРѕСЃС‚СѓРїР° РѕР±СЂР°С‚РёС‚РµСЃСЊ Рє Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ.",
            parse_mode="HTML",
        )
        return

    lines = [
        "<b>Р”РѕСЃС‚СѓРїРЅС‹Рµ РєРѕРјР°РЅРґС‹</b>\n",
        "/start вЂ” Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ",
        "/raspisanie вЂ” Р Р°СЃРїРёСЃР°РЅРёРµ СѓСЂРѕРєРѕРІ",
        "/dz вЂ” Р”РѕРјР°С€РЅРёРµ Р·Р°РґР°РЅРёСЏ",
        "/test вЂ” РџСЂРѕР№С‚Рё С‚РµСЃС‚ РїРѕ СЏР·С‹РєСѓ",
        "/social вЂ” РЎРѕСЂРµРІРЅРѕРІР°РЅРёСЏ Рё СЃРѕС†-С„СѓРЅРєС†РёРё",
        "/share &lt;token&gt; вЂ” РћС‚РєСЂС‹С‚СЊ shared-СЂРµР·СѓР»СЊС‚Р°С‚",
        "/settings вЂ” РќР°СЃС‚СЂРѕР№РєРё СѓРІРµРґРѕРјР»РµРЅРёР№",
        "/remind вЂ” Р›РёС‡РЅС‹Рµ РµР¶РµРґРЅРµРІРЅС‹Рµ РЅР°РїРѕРјРёРЅР°РЅРёСЏ",
        "/profile вЂ” РњРѕР№ РїСЂРѕС„РёР»СЊ",
        "/report — PDF-отчеты (расписание/оценки)",
        "/help вЂ” РЎРїСЂР°РІРєР° (СЌС‚Р° СЃС‚СЂР°РЅРёС†Р°)",
    ]

    if role in ("admin", "parent"):
        lines.append("/ocenki вЂ” РћС†РµРЅРєРё")
        lines.append("/import_questions вЂ” РРјРїРѕСЂС‚ РІРѕРїСЂРѕСЃРѕРІ РёР· JSON")

    if role == "admin":
        lines.append("\n<b>РљРѕРјР°РЅРґС‹ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂР°</b>")
        lines.append("/allow &lt;id&gt; [student|parent|admin] вЂ” Р”РѕР±Р°РІРёС‚СЊ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ")
        lines.append("/block &lt;id&gt; вЂ” Р—Р°Р±Р»РѕРєРёСЂРѕРІР°С‚СЊ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ")
        lines.append("/users вЂ” РЎРїРёСЃРѕРє РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№")
        lines.append("/health вЂ” РџСЂРѕРІРµСЂРєР° СЃРѕСЃС‚РѕСЏРЅРёСЏ Р±РѕС‚Р°")

    lines.append("\n<i>РСЃРїРѕР»СЊР·СѓР№С‚Рµ РєРЅРѕРїРєРё РјРµРЅСЋ РґР»СЏ СѓРґРѕР±РЅРѕР№ РЅР°РІРёРіР°С†РёРё.</i>")

    kb = InlineKeyboardMarkup(inline_keyboard=[[home_button()]])
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.message(Command("testauth"))
async def cmd_test_auth(message: Message):
    """Р”РёР°РіРЅРѕСЃС‚РёРєР° СЃРѕРµРґРёРЅРµРЅРёСЏ СЃ РњР­РЁ вЂ” С‚РµСЃС‚ РёР·РЅСѓС‚СЂРё Р±РѕС‚Р°."""
    await message.answer("Р—Р°РїСѓСЃРєР°СЋ РґРёР°РіРЅРѕСЃС‚РёРєСѓ РњР­РЁ СЃРѕРµРґРёРЅРµРЅРёСЏ...")

    from octodiary.apis.async_ import AsyncMobileAPI
    from octodiary.urls import Systems
    from octodiary.exceptions import APIError

    results = []

    # РўРµСЃС‚ 1: aiohttp Р±РµР· wait_for
    t = time.time()
    api = AsyncMobileAPI(system=Systems.MES)
    try:
        await api.login("diag_test@test.ru", "WrongPass_Diag1")
        results.append(f"РўРµСЃС‚ 1: РќР•РћР–РР”РђРќРќР«Р™ РЈРЎРџР•РҐ ({time.time()-t:.2f}СЃ)")
    except aiohttp.ConnectionTimeoutError:
        elapsed = time.time() - t
        results.append(
            f"РўРµСЃС‚ 1 ({elapsed:.2f}СЃ): OctoDiary connect timeout вЂ” "
            f"TCP+TLS РЅРµ Р·Р°РІРµСЂС€РёР»СЃСЏ Р·Р° {elapsed:.0f}СЃ"
        )
    except aiohttp.ClientConnectorError as e:
        elapsed = time.time() - t
        results.append(f"РўРµСЃС‚ 1 ({elapsed:.2f}СЃ): DNS/connect error вЂ” {str(e)[:60]}")
    except asyncio.TimeoutError:
        elapsed = time.time() - t
        results.append(f"РўРµСЃС‚ 1 ({elapsed:.2f}СЃ): asyncio timeout")
    except APIError as e:
        elapsed = time.time() - t
        results.append(
            f"РўРµСЃС‚ 1 ({elapsed:.2f}СЃ): APIError вЂ” {e.error_types} "
            f"(РЎР•РўР¬ Р РђР‘РћРўРђР•Рў)"
        )
    except Exception as e:
        elapsed = time.time() - t
        results.append(f"РўРµСЃС‚ 1 ({elapsed:.2f}СЃ): {type(e).__name__}: {str(e)[:60]}")
    finally:
        await _close_octodiary_session(api)

    # РўРµСЃС‚ 2: aiohttp СЃ wait_for(15СЃ)
    t = time.time()
    api = AsyncMobileAPI(system=Systems.MES)
    try:
        await asyncio.wait_for(
            api.login("diag_test2@test.ru", "WrongPass_Diag2"),
            timeout=15,
        )
        results.append(f"РўРµСЃС‚ 2: РќР•РћР–РР”РђРќРќР«Р™ РЈРЎРџР•РҐ ({time.time()-t:.2f}СЃ)")
    except aiohttp.ConnectionTimeoutError:
        elapsed = time.time() - t
        results.append(
            f"РўРµСЃС‚ 2 ({elapsed:.2f}СЃ): OctoDiary connect timeout вЂ” "
            f"TCP+TLS РЅРµ Р·Р°РІРµСЂС€РёР»СЃСЏ Р·Р° {elapsed:.0f}СЃ"
        )
    except aiohttp.ClientConnectorError as e:
        elapsed = time.time() - t
        results.append(f"РўРµСЃС‚ 2 ({elapsed:.2f}СЃ): DNS/connect error вЂ” {str(e)[:60]}")
    except asyncio.TimeoutError:
        elapsed = time.time() - t
        results.append(f"РўРµСЃС‚ 2 ({elapsed:.2f}СЃ): asyncio.wait_for(15СЃ) РёСЃС‚С‘Рє")
    except APIError as e:
        elapsed = time.time() - t
        results.append(
            f"РўРµСЃС‚ 2 ({elapsed:.2f}СЃ): APIError вЂ” {e.error_types} "
            f"(РЎР•РўР¬ Р РђР‘РћРўРђР•Рў)"
        )
    except Exception as e:
        elapsed = time.time() - t
        results.append(f"РўРµСЃС‚ 2 ({elapsed:.2f}СЃ): {type(e).__name__}: {str(e)[:60]}")
    finally:
        await _close_octodiary_session(api)

    # РўРµСЃС‚ 3: С‡РёСЃС‚С‹Р№ TCP (Р±РµР· TLS)
    t = time.time()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("login.mos.ru", 443),
            timeout=5,
        )
        writer.close()
        await writer.wait_closed()
        results.append(f"РўРµСЃС‚ 3 ({time.time()-t:.2f}СЃ): TCP OK вЂ” login.mos.ru:443 РґРѕСЃС‚СѓРїРµРЅ")
    except asyncio.TimeoutError:
        results.append(f"РўРµСЃС‚ 3 ({time.time()-t:.2f}СЃ): TCP TIMEOUT вЂ” РїРѕСЂС‚ 443 РЅРµ РѕС‚РІРµС‡Р°РµС‚")
    except OSError as e:
        results.append(f"РўРµСЃС‚ 3 ({time.time()-t:.2f}СЃ): TCP ERROR вЂ” {str(e)[:60]}")

    # РўРµСЃС‚ 4: TCP + TLS handshake (Python/OpenSSL)
    t = time.time()
    try:
        ssl_ctx = _ssl.create_default_context()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("login.mos.ru", 443, ssl=ssl_ctx),
            timeout=30,
        )
        writer.close()
        await writer.wait_closed()
        results.append(f"РўРµСЃС‚ 4 ({time.time()-t:.2f}СЃ): TLS OK вЂ” Python/OpenSSL handshake")
    except asyncio.TimeoutError:
        results.append(f"РўРµСЃС‚ 4 ({time.time()-t:.2f}СЃ): TLS TIMEOUT >30СЃ вЂ” OpenSSL Р·Р°Р±Р»РѕРєРёСЂРѕРІР°РЅ (JA3)")
    except OSError as e:
        results.append(f"РўРµСЃС‚ 4 ({time.time()-t:.2f}СЃ): TLS ERROR вЂ” {str(e)[:60]}")

    # РўРµСЃС‚ 5: curl_cffi GET Рє root login.mos.ru
    t = time.time()
    try:
        from curl_cffi.requests import AsyncSession
        async with AsyncSession(impersonate="chrome124") as s:
            resp = await s.get("https://login.mos.ru/", allow_redirects=False)
        results.append(
            f"РўРµСЃС‚ 5 ({time.time()-t:.2f}СЃ): curl_cffi OK вЂ” HTTP {resp.status_code}"
        )
    except ImportError:
        results.append("РўРµСЃС‚ 5: curl_cffi РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ (pip install curl-cffi)")
    except Exception as e:
        elapsed = time.time() - t
        results.append(f"РўРµСЃС‚ 5 ({elapsed:.2f}СЃ): curl_cffi ERROR вЂ” {str(e)[:80]}")

    # РўРµСЃС‚ 6: curl_cffi POST Рє /sps/oauth/register (РїРµСЂРІС‹Р№ СЂРµР°Р»СЊРЅС‹Р№ С€Р°Рі OAuth)
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
            f"РўРµСЃС‚ 6 ({time.time()-t:.2f}СЃ): OAuth API OK вЂ” HTTP {resp.status_code} "
            f"(curl_cffi РґРѕСЃС‚РёРіР°РµС‚ API РњР­РЁ!)"
        )
    except ImportError:
        results.append("РўРµСЃС‚ 6: curl_cffi РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ")
    except Exception as e:
        elapsed = time.time() - t
        results.append(f"РўРµСЃС‚ 6 ({elapsed:.2f}СЃ): OAuth API ERROR вЂ” {str(e)[:80]}")

    report = "\n".join(results)

    # Р”РёРЅР°РјРёС‡РµСЃРєР°СЏ СЂР°СЃС€РёС„СЂРѕРІРєР° РЅР° РѕСЃРЅРѕРІРµ СЂРµР°Р»СЊРЅС‹С… СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ
    test2_ok = any("РЎР•РўР¬ Р РђР‘РћРўРђР•Рў" in r for r in results)
    test4_timeout = any("РўРµСЃС‚ 4" in r and "TIMEOUT" in r for r in results)
    test5_ok = any("РўРµСЃС‚ 5" in r and "OK" in r for r in results)
    test6_ok = any("РўРµСЃС‚ 6" in r and "OK" in r for r in results)

    hints = ["\n\nР Р°СЃС€РёС„СЂРѕРІРєР°:"]
    if test2_ok:
        hints.append("вњ… РўРµСЃС‚ 2 OK вЂ” curl_cffi СЂР°Р±РѕС‚Р°РµС‚, OAuth-С€Р°РіРё 1-3 РїСЂРѕС…РѕРґСЏС‚")
    else:
        hints.append("вќЊ РўРµСЃС‚ 2 FAIL вЂ” СЃРѕРµРґРёРЅРµРЅРёРµ СЃ РњР­РЁ РЅРµ СЂР°Р±РѕС‚Р°РµС‚")

    if test4_timeout and test2_ok:
        hints.append("вњ… РўРµСЃС‚ 4 TIMEOUT + РўРµСЃС‚ 2 OK вЂ” JA3 РѕР±С…РѕРґРёС‚СЃСЏ С‡РµСЂРµР· curl_cffi")
    elif not test4_timeout:
        hints.append("вљ пёЏ РўРµСЃС‚ 4 OK вЂ” Python/OpenSSL РЅРµ Р·Р°Р±Р»РѕРєРёСЂРѕРІР°РЅ (РЅРµРѕР¶РёРґР°РЅРЅРѕ)")

    if test6_ok:
        hints.append("вњ… РўРµСЃС‚ 6 OK вЂ” РїСЂСЏРјРѕР№ POST Рє OAuth API СЂР°Р±РѕС‚Р°РµС‚")
    elif test2_ok:
        hints.append("вљ пёЏ РўРµСЃС‚ 6 ERROR РїСЂРё РўРµСЃС‚ 2 OK вЂ” РІРѕР·РјРѕР¶РЅР° РїСЂРѕР±Р»РµРјР° СЃРѕ software_statement")
    else:
        hints.append("вќЊ РўРµСЃС‚ 6 ERROR вЂ” curl_cffi РЅРµ РґРѕСЃС‚РёРіР°РµС‚ OAuth API")

    if test5_ok:
        hints.append("в„№пёЏ РўРµСЃС‚ 5 OK вЂ” root login.mos.ru РґРѕСЃС‚СѓРїРµРЅ")
    elif test2_ok:
        hints.append("в„№пёЏ РўРµСЃС‚ 5 ERROR РїСЂРё РўРµСЃС‚ 2 OK вЂ” root Р±Р»РѕРєРёСЂРѕРІР°РЅ, РЅРѕ API СЂР°Р±РѕС‚Р°РµС‚ (РЅРѕСЂРјР°)")
    else:
        hints.append("вќЊ РўРµСЃС‚ 5 ERROR вЂ” login.mos.ru РЅРµРґРѕСЃС‚СѓРїРµРЅ РґР°Р¶Рµ С‡РµСЂРµР· curl_cffi")

    if test2_ok and not test6_ok:
        hints.append("\nрџ”Ќ Р’РµСЂРѕСЏС‚РЅР°СЏ РїСЂРёС‡РёРЅР° РѕС€РёР±РєРё РІС…РѕРґР°: С€Р°Рі 4+ OAuth (sms/bind РёР»Рё /sps/oauth/te)")
    elif not test2_ok:
        hints.append("\nрџ”ґ РђРІС‚РѕСЂРёР·Р°С†РёСЏ РЅРµРІРѕР·РјРѕР¶РЅР° вЂ” РїСЂРѕРІРµСЂСЊС‚Рµ СЃРµС‚РµРІРѕРµ РїРѕРґРєР»СЋС‡РµРЅРёРµ")

    hint = "\n".join(hints)
    logger.info("Auth diagnostic:\n%s", report)
    await message.answer(f"Р РµР·СѓР»СЊС‚Р°С‚С‹:\n{report}{hint}")


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start вЂ” role-based menu."""
    await state.clear()
    user_id = message.from_user.id

    # РџСЂРѕРІРµСЂСЏРµРј, РµСЃС‚СЊ Р»Рё РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ РІ Р‘Р”
    if not await user_exists(user_id):
        # РђРІС‚РѕРІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёРµ РіР»Р°РІРЅРѕРіРѕ Р°РґРјРёРЅР° (РјРѕРі СѓРґР°Р»РёС‚СЊСЃСЏ РїСЂРё РїРµСЂРµСЂРµРіРёСЃС‚СЂР°С†РёРё)
        if settings.ADMIN_ID and user_id == settings.ADMIN_ID:
            await set_user_access(user_id, "admin")
            logger.info("РђРІС‚РѕРІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёРµ Р°РґРјРёРЅР° user_id=%d", user_id)
        else:
            await message.answer(
                "вќ— Р”РѕСЃС‚СѓРї РѕРіСЂР°РЅРёС‡РµРЅ.\n\n"
                "Р”Р»СЏ РїРѕР»СѓС‡РµРЅРёСЏ РґРѕСЃС‚СѓРїР° РѕР±СЂР°С‚РёС‚РµСЃСЊ Рє Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ."
            )
            return

    role = await get_user_role(user_id)

    if role == "admin":
        await _set_user_commands(message.bot, user_id, role)
        await message.answer(
            "рџ‘‹ РЎ РІРѕР·РІСЂР°С‰РµРЅРёРµРј, Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ!\n\n"
            "Р’С‹Р±РµСЂРёС‚Рµ РґРµР№СЃС‚РІРёРµ:",
            reply_markup=full_menu_keyboard(),
        )

    elif role == "parent":
        await _set_user_commands(message.bot, user_id, role)
        user = await get_user(user_id)
        has_mesh = user and user.get("mesh_login")
        if has_mesh:
            await message.answer(
                "рџ‘‹ РЎ РІРѕР·РІСЂР°С‰РµРЅРёРµРј!\n\n"
                "Р’С‹Р±РµСЂРёС‚Рµ РґРµР№СЃС‚РІРёРµ:",
                reply_markup=full_menu_keyboard(),
            )
        else:
            await message.answer(
                "рџ‘‹ Р”РѕР±СЂРѕ РїРѕР¶Р°Р»РѕРІР°С‚СЊ!\n\n"
                "Р”Р»СЏ РґРѕСЃС‚СѓРїР° Рє СЂР°СЃРїРёСЃР°РЅРёСЋ, РѕС†РµРЅРєР°Рј Рё Р”Р—\n"
                "РЅРµРѕР±С…РѕРґРёРјРѕ РІРѕР№С‚Рё РІ СЃРёСЃС‚РµРјСѓ РњР­РЁ.\n\n"
                "Р’РІРµРґРёС‚Рµ РІР°С€ Р»РѕРіРёРЅ РѕС‚ dnevnik.mos.ru:"
            )
            await state.set_state(RegistrationStates.waiting_for_mesh_login)

    elif role == "student":
        await ensure_quiz_user(user_id, message.from_user.username, message.from_user.first_name)
        await _set_user_commands(message.bot, user_id, role)
        user = await get_user(user_id)
        has_mesh = user and user.get("mesh_login")
        if has_mesh:
            await message.answer(
                "рџ‘‹ РџСЂРёРІРµС‚! РЇ РЁРєРѕР»СЊРЅС‹Р№ РїРѕРјРѕС‰РЅРёРє.\n\n"
                "Р’С‹Р±РµСЂРё, С‡С‚Рѕ С…РѕС‡РµС€СЊ СЃРґРµР»Р°С‚СЊ:",
                reply_markup=student_menu_keyboard(),
            )
        else:
            await message.answer(
                "рџ‘‹ РџСЂРёРІРµС‚! РЇ РЁРєРѕР»СЊРЅС‹Р№ РїРѕРјРѕС‰РЅРёРє.\n\n"
                "Р”Р»СЏ РґРѕСЃС‚СѓРїР° Рє СЂР°СЃРїРёСЃР°РЅРёСЋ Рё РґРѕРјР°С€РЅРёРј Р·Р°РґР°РЅРёСЏРј\n"
                "РЅРµРѕР±С…РѕРґРёРјРѕ РІРѕР№С‚Рё РІ СЃРёСЃС‚РµРјСѓ РњР­РЁ.\n\n"
                "Р’РІРµРґРёС‚Рµ РІР°С€ Р»РѕРіРёРЅ РѕС‚ dnevnik.mos.ru:"
            )
            await state.set_state(RegistrationStates.waiting_for_mesh_login)

    else:
        await message.answer("вќ— Р РѕР»СЊ РЅРµ РѕРїСЂРµРґРµР»РµРЅР°. РћР±СЂР°С‚РёС‚РµСЃСЊ Рє Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ.")



@router.callback_query(F.data == "go_home")
async def go_home(callback: CallbackQuery, state: FSMContext):
    """Return to main menu based on role."""
    await state.clear()
    user_id = callback.from_user.id
    role = await get_user_role(user_id)

    if role == "student":
        await callback.message.edit_text(
            "рџ‘‹ Р’С‹Р±РµСЂРё, С‡С‚Рѕ С…РѕС‡РµС€СЊ СЃРґРµР»Р°С‚СЊ:",
            reply_markup=student_menu_keyboard(),
        )
    else:
        await callback.message.edit_text("Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ:", reply_markup=full_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "reregister")
async def cb_reregister(callback: CallbackQuery, state: FSMContext):
    """РџРµСЂРµСЂРµРіРёСЃС‚СЂР°С†РёСЏ: СѓРґР°Р»РёС‚СЊ СЃС‚Р°СЂС‹Рµ РґР°РЅРЅС‹Рµ Рё РЅР°С‡Р°С‚СЊ Р·Р°РЅРѕРІРѕ."""
    user_id = callback.from_user.id

    # РЎРѕС…СЂР°РЅСЏРµРј СЂРѕР»СЊ РїРµСЂРµРґ СѓРґР°Р»РµРЅРёРµРј
    role = await get_user_role(user_id)

    await delete_user(user_id)
    await state.clear()

    # Р’РѕСЃСЃС‚Р°РЅР°РІР»РёРІР°РµРј СЂРѕР»СЊ, С‡С‚РѕР±С‹ РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РїРѕС‚РµСЂСЏР» РґРѕСЃС‚СѓРї
    if role:
        await set_user_access(user_id, role)

    logger.info("РџРµСЂРµСЂРµРіРёСЃС‚СЂР°С†РёСЏ: РњР­РЁ-РґР°РЅРЅС‹Рµ СѓРґР°Р»РµРЅС‹, СЂРѕР»СЊ %s СЃРѕС…СЂР°РЅРµРЅР°, user_id=%d", role, user_id)

    await callback.message.edit_text(
        "РЎС‚Р°СЂС‹Рµ РґР°РЅРЅС‹Рµ СѓРґР°Р»РµРЅС‹.\n\n"
        "Р’РІРµРґРёС‚Рµ РІР°С€ Р»РѕРіРёРЅ РѕС‚ dnevnik.mos.ru:"
    )
    await state.set_state(RegistrationStates.waiting_for_mesh_login)
    await callback.answer()


