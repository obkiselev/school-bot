"""Admin commands: /allow, /block, /users."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup

from config import settings
from database.crud import is_user_allowed, set_user_access, block_user, get_all_users_list
from keyboards.main_menu import home_button

router = Router()

VALID_ROLES = {"student", "admin", "parent"}

_home_kb = InlineKeyboardMarkup(inline_keyboard=[[home_button()]])


async def _check_admin(message: Message) -> bool:
    """Check that sender is admin and chat is private."""
    if message.chat.type != "private":
        await message.answer("Команда доступна только в личных сообщениях.")
        return False
    allowed, role = await is_user_allowed(message.from_user.id)
    if not allowed or role != "admin":
        return False
    return True


@router.message(Command("allow"))
async def cmd_allow(message: Message):
    """Add a user with a role: /allow <user_id> [student|parent|admin]"""
    if not await _check_admin(message):
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "Формат: /allow <user_id> [student|parent|admin]\n"
            "Пример: /allow 123456789 student"
        )
        return

    raw_id = parts[1]
    if not raw_id.isdigit():
        await message.answer("user_id должен быть числом.")
        return

    target_id = int(raw_id)
    role = "student"
    if len(parts) >= 3:
        role = parts[2].lower()
        if role not in VALID_ROLES:
            await message.answer(f"Неизвестная роль: {role}\nДоступные: student, parent, admin")
            return

    await set_user_access(target_id, role)

    role_labels = {"student": "📚 ученик", "parent": "👨‍👩‍👧 родитель", "admin": "👑 админ"}
    await message.answer(
        f"✅ Пользователь {target_id} добавлен ({role_labels.get(role, role)})",
        reply_markup=_home_kb,
    )


@router.message(Command("block"))
async def cmd_block(message: Message):
    """Block a user: /block <user_id>"""
    if not await _check_admin(message):
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Формат: /block <user_id>")
        return

    raw_id = parts[1]
    if not raw_id.isdigit():
        await message.answer("user_id должен быть числом.")
        return

    target_id = int(raw_id)

    if target_id == message.from_user.id:
        await message.answer("Нельзя заблокировать самого себя.")
        return

    if settings.ADMIN_ID and target_id == settings.ADMIN_ID:
        await message.answer("Нельзя заблокировать главного администратора.")
        return

    allowed, role = await is_user_allowed(target_id)
    if role is not None and not allowed:
        await message.answer("Пользователь уже заблокирован.")
        return

    result = await block_user(target_id)
    if not result:
        await message.answer("Пользователь не найден в базе.")
        return

    await message.answer(f"🚫 Пользователь {target_id} заблокирован.", reply_markup=_home_kb)


@router.message(Command("users"))
async def cmd_users(message: Message):
    """List all users: /users"""
    if not await _check_admin(message):
        return

    users = await get_all_users_list()
    if not users:
        await message.answer("Список пользователей пуст.")
        return

    lines = ["👥 Список пользователей:\n"]
    for u in users:
        name = u["first_name"] or u["username"] or str(u["user_id"])
        status = "🚫 заблокирован" if u["is_blocked"] else "✅ активен"
        role_labels = {"admin": "👑 admin", "parent": "👨‍👩‍👧 parent", "student": "📚 student"}
        role_label = role_labels.get(u["role"], u["role"] or "?")
        lines.append(f"• {name} (ID: {u['user_id']}) — {role_label}, {status}")

    await message.answer("\n".join(lines), reply_markup=_home_kb)
