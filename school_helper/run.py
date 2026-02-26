import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN
from bot.handlers import start, language, topic, settings, quiz, results, history


async def main():
    if not BOT_TOKEN:
        print("Ошибка: BOT_TOKEN не задан. Создайте файл .env на основе .env.example")
        sys.exit(1)

    # Инициализируем базу данных
    from bot.db.database import get_db, close_db
    await get_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Подключаем все роутеры
    dp.include_router(start.router)
    dp.include_router(language.router)
    dp.include_router(topic.router)
    dp.include_router(settings.router)
    dp.include_router(quiz.router)
    dp.include_router(results.router)
    dp.include_router(history.router)

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    print("Бот запущен! Нажмите Ctrl+C для остановки.")

    try:
        await dp.start_polling(bot)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
