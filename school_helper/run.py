import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import BOT_TOKEN
from bot.handlers import admin, start, language, topic, settings, quiz, results, history
from bot.middleware.access import AccessControlMiddleware


async def main():
    if not BOT_TOKEN:
        print("Ошибка: BOT_TOKEN не задан. Создайте файл .env на основе .env.example")
        sys.exit(1)

    # Инициализируем базу данных
    from bot.db.database import get_db, close_db
    await get_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware контроля доступа
    dp.message.outer_middleware(AccessControlMiddleware())
    dp.callback_query.outer_middleware(AccessControlMiddleware())

    # Подключаем все роутеры (admin первым)
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(language.router)
    dp.include_router(topic.router)
    dp.include_router(settings.router)
    dp.include_router(quiz.router)
    dp.include_router(results.router)
    dp.include_router(history.router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="allow", description="Добавить пользователя (админ)"),
        BotCommand(command="block", description="Заблокировать пользователя (админ)"),
        BotCommand(command="users", description="Список пользователей (админ)"),
    ])

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    print("Бот запущен! Нажмите Ctrl+C для остановки.")

    try:
        await dp.start_polling(bot)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
