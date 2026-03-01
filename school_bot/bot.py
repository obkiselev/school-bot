"""Main entry point for School Bot."""
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from core import database

# Import handlers
from handlers import start, registration, schedule


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Всегда показываем пошаговые логи авторизации для диагностики
logging.getLogger("octodiary.auth").setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)


async def main():
    """Main function to start the bot."""
    logger.info("Starting МЭШ School Bot...")

    # Initialize database
    logger.info(f"Initializing database at {settings.DATABASE_PATH}")
    db = await database.init_database(settings.DATABASE_PATH)
    database.db = db  # Set global instance

    # Initialize bot and dispatcher
    bot = Bot(token=settings.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register routers
    dp.include_router(start.router)
    dp.include_router(registration.router)
    dp.include_router(schedule.router)

    logger.info("Bot handlers registered successfully")

    # Start polling
    try:
        logger.info("Starting bot polling...")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types()
        )
    except Exception as e:
        logger.error(f"Error during polling: {e}")
        raise
    finally:
        # Cleanup
        await bot.session.close()
        if db:
            await db.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
