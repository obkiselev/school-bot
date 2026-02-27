from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import ADMIN_ID
from bot.db.queries import is_user_allowed, set_user_access, block_user, get_all_users_list

router = Router()

VALID_ROLES = {"student", "admin"}


async def _check_admin(message: Message) -> bool:
    """Check that sender is admin and chat is private. Returns True if OK."""
    if message.chat.type != "private":
        await message.answer("⚠️ Команда доступна только в личных сообщениях.")
        return False
    allowed, role = await is_user_allowed(message.from_user.id)
    if not allowed or role != "admin":
        return False
    return True


@router.message(Command("allow"))
async def cmd_allow(message: Message):
    if not await _check_admin(message):
        return

    parts = message.text.split()
    # /allow <user_id> [role]
    if len(parts) < 2:
        await message.answer("Формат: /allow <user_id> [student|admin]\nПример: /allow 123456789")
        return

    raw_id = parts[1]
    if not raw_id.isdigit():
        await message.answer("Формат: /allow <user_id> [student|admin]\nuser_id должен быть числом.")
        return

    target_id = int(raw_id)
    role = "student"
    if len(parts) >= 3:
        role = parts[2].lower()
        if role not in VALID_ROLES:
            await message.answer(f"Неизвестная роль: {role}\nДоступные роли: student, admin")
            return

    await set_user_access(target_id, role)
    await message.answer(f"✅ Пользователь {target_id} добавлен (роль: {role})")


@router.message(Command("block"))
async def cmd_block(message: Message):
    if not await _check_admin(message):
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Формат: /block <user_id>\nПример: /block 123456789")
        return

    raw_id = parts[1]
    if not raw_id.isdigit():
        await message.answer("Формат: /block <user_id>\nuser_id должен быть числом.")
        return

    target_id = int(raw_id)

    # Protection: can't block yourself
    if target_id == message.from_user.id:
        await message.answer("❌ Нельзя заблокировать самого себя.")
        return

    # Protection: can't block primary admin
    if ADMIN_ID is not None and target_id == ADMIN_ID:
        await message.answer("❌ Нельзя заблокировать главного администратора.")
        return

    # Check if already blocked
    allowed, role = await is_user_allowed(target_id)
    if role is not None and not allowed:
        await message.answer("Пользователь уже заблокирован.")
        return

    result = await block_user(target_id)
    if not result:
        await message.answer("Пользователь не найден в базе.")
        return

    await message.answer(f"🚫 Пользователь {target_id} заблокирован.")


@router.message(Command("users"))
async def cmd_users(message: Message):
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
        role_label = "👑 admin" if u["role"] == "admin" else "📚 student"
        lines.append(f"• {name} (ID: {u['user_id']}) — {role_label}, {status}")

    await message.answer("\n".join(lines))
