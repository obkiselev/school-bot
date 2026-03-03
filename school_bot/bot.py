"""Main entry point for School Bot."""
import asyncio
import logging
import logging.handlers
import os
import socket
import subprocess
import sys
import threading
import time
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import settings
from core import database
import mesh_api.proxy_patch  # noqa: F401 — патч OctoDiary для SOCKS5 прокси

# Import handlers
from handlers import start, registration, schedule
from handlers import quiz, language, topic, quiz_settings, history, admin
from middlewares.access import AccessControlMiddleware


# Configure logging — stdout + файл (data/logs/bot.log)
_log_dir = os.path.join(os.path.dirname(__file__), "data", "logs")
os.makedirs(_log_dir, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            os.path.join(_log_dir, "bot.log"),
            maxBytes=5 * 1024 * 1024,  # 5 МБ
            backupCount=3,
            encoding="utf-8",
        ),
    ]
)

# Всегда показываем пошаговые логи авторизации для диагностики
logging.getLogger("octodiary.auth").setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)


def _read_stderr_thread(pipe, buffer: list):
    """Фоновый поток для чтения stderr SSH (select() не работает на Windows)."""
    try:
        for line in pipe:
            if isinstance(line, bytes):
                line = line.decode(errors="replace")
            buffer.append(line)
    except Exception:
        pass


def _get_tunnel_port() -> int:
    """Локальный порт SOCKS5 из MESH_PROXY_URL (по умолчанию 1080)."""
    proxy_url = getattr(settings, "MESH_PROXY_URL", "") or ""
    if ":" in proxy_url:
        try:
            return int(proxy_url.rsplit(":", 1)[-1])
        except ValueError:
            pass
    return 1080


def _wait_for_port(host: str, port: int, timeout: float = 15.0) -> bool:
    """Ждёт пока host:port начнёт принимать TCP-соединения (до timeout сек)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def _kill_stale_ssh_tunnels(local_port: int) -> None:
    """Убивает зомби SSH-процессы, оставшиеся от предыдущих запусков бота."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if f":{local_port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                if not pid.isdigit():
                    continue
                logger.warning("SSH-туннель: убиваю зомби-процесс PID %s на порту %d",
                               pid, local_port)
                subprocess.run(
                    ["taskkill", "/PID", pid, "/F"],
                    capture_output=True, timeout=5,
                )
    except Exception as e:
        logger.debug("Не удалось проверить зомби-процессы: %s", e)


_SSH_MAX_RETRIES = 3
_SSH_TIMEOUT = 30.0


def _start_ssh_tunnel() -> subprocess.Popen | None:
    """Запускает SSH-туннель (SOCKS5 прокси) если настроен MESH_SSH_PROXY.

    Читает параметры из .env:
      MESH_SSH_PROXY=true          — включить SSH-туннель
      MESH_SSH_HOST=45.152.113.91  — адрес сервера
      MESH_SSH_PORT=4422           — SSH-порт
      MESH_SSH_USER=life_sync      — пользователь
      MESH_SSH_KEY=~/.ssh/id_ed25519_rag  — путь к ключу
      MESH_PROXY_URL=socks5://127.0.0.1:1080  — уже должен быть настроен

    Убивает зомби-процессы на порту, до 3 попыток с таймаутом 30 сек.
    """
    if not getattr(settings, "MESH_SSH_PROXY", False):
        return None

    host = getattr(settings, "MESH_SSH_HOST", "")
    port = getattr(settings, "MESH_SSH_PORT", 22)
    user = getattr(settings, "MESH_SSH_USER", "")
    key_path = getattr(settings, "MESH_SSH_KEY", "")

    if not host or not user:
        logger.warning("SSH-туннель: MESH_SSH_HOST или MESH_SSH_USER не заданы")
        return None

    local_port = _get_tunnel_port()

    # Git SSH вместо зависающего Windows OpenSSH
    # Если MESH_SSH_PATH задан — используем его, иначе ищем Git SSH автоматически
    ssh_exe = getattr(settings, "MESH_SSH_PATH", "") or ""
    if ssh_exe:
        ssh_exe = os.path.expanduser(ssh_exe).replace("\\", "/")
        if not os.path.isfile(ssh_exe):
            logger.warning("SSH-туннель: SSH-клиент не найден: %s, ищу Git SSH...", ssh_exe)
            ssh_exe = ""
    if not ssh_exe:
        # Автопоиск Git SSH на известных компьютерах (Kata-17, Lenovo и др.)
        _git_ssh_candidates = [
            "E:/Progs/Git/usr/bin/ssh.exe",        # Kata-17
            "D:/Programs/Git/usr/bin/ssh.exe",      # Lenovo
            "C:/Program Files/Git/usr/bin/ssh.exe", # стандартная установка
        ]
        for candidate in _git_ssh_candidates:
            if os.path.isfile(candidate):
                ssh_exe = candidate
                logger.info("SSH-туннель: найден Git SSH: %s", ssh_exe)
                break
        if not ssh_exe:
            ssh_exe = "ssh"
            logger.warning("SSH-туннель: Git SSH не найден, использую системный ssh")

    cmd = [
        ssh_exe,
        "-D", str(local_port),       # SOCKS5 прокси
        "-N",                         # без оболочки
        "-v",                         # подробный вывод для диагностики
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "BatchMode=yes",        # без интерактивных запросов (пароль/passphrase)
        "-p", str(port),
    ]
    if key_path:
        key_path = os.path.expanduser(key_path).replace("\\", "/")
        if not os.path.isfile(key_path):
            logger.warning("SSH-туннель: файл ключа не найден: %s", key_path)
        cmd.extend(["-i", key_path])
    cmd.append(f"{user}@{host}")

    logger.info("SSH-туннель: команда: %s", " ".join(cmd))

    for attempt in range(1, _SSH_MAX_RETRIES + 1):
        logger.info("SSH-туннель: попытка %d/%d — SOCKS5 на 127.0.0.1:%d через %s@%s:%s",
                     attempt, _SSH_MAX_RETRIES, local_port, user, host, port)

        _kill_stale_ssh_tunnels(local_port)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            # Фоновый поток для чтения stderr (select не работает на Windows)
            stderr_lines: list[str] = []
            stderr_thread = threading.Thread(
                target=_read_stderr_thread, args=(proc.stderr, stderr_lines), daemon=True
            )
            stderr_thread.start()

            # Ждём пока порт реально откроется
            if _wait_for_port("127.0.0.1", local_port, timeout=_SSH_TIMEOUT):
                logger.info("SSH-туннель: SOCKS5 прокси готов на 127.0.0.1:%d (PID %d)",
                            local_port, proc.pid)
                return proc

            # Порт не открылся — собираем диагностику
            stderr_thread.join(timeout=2.0)
            stderr = "".join(stderr_lines).strip()

            if proc.poll() is not None:
                logger.error("SSH-туннель: попытка %d/%d — процесс завершился (код %d):\n%s",
                             attempt, _SSH_MAX_RETRIES, proc.returncode, stderr)
            else:
                logger.error("SSH-туннель: попытка %d/%d — процесс жив (PID %d), "
                             "но порт %d не слушает после %.0f сек:\n%s",
                             attempt, _SSH_MAX_RETRIES, proc.pid, local_port,
                             _SSH_TIMEOUT, stderr or "(пусто)")
                proc.kill()
                proc.wait(timeout=5)

            if attempt < _SSH_MAX_RETRIES:
                logger.info("SSH-туннель: повтор через 3 сек...")
                time.sleep(3)

        except FileNotFoundError:
            logger.error("SSH-туннель: команда ssh не найдена")
            return None
        except Exception as e:
            logger.error("SSH-туннель: ошибка запуска: %s", e)
            if attempt < _SSH_MAX_RETRIES:
                time.sleep(3)

    # Все попытки исчерпаны — проверяем доступность удалённого сервера
    try:
        with socket.create_connection((host, int(port)), timeout=5.0):
            logger.error("SSH-туннель: все %d попыток провалились, "
                         "но сервер %s:%s TCP-доступен", _SSH_MAX_RETRIES, host, port)
    except OSError as e:
        logger.error("SSH-туннель: все %d попыток провалились, "
                     "сервер %s:%s НЕ доступен: %s", _SSH_MAX_RETRIES, host, port, e)
    return None


# Глобальная ссылка на процесс SSH-туннеля (для мониторинга и перезапуска)
_ssh_tunnel_proc: subprocess.Popen | None = None


async def _monitor_ssh_tunnel():
    """Фоновая задача: проверяет SSH-туннель каждые 30 сек, перезапускает при падении."""
    global _ssh_tunnel_proc
    local_port = _get_tunnel_port()

    while True:
        await asyncio.sleep(30)
        if _ssh_tunnel_proc is None:
            logger.info("SSH-туннель: нет активного туннеля, пробую запустить...")
            _ssh_tunnel_proc = _start_ssh_tunnel()
            continue

        # Проверка 1: процесс жив?
        if _ssh_tunnel_proc.poll() is not None:
            logger.warning("SSH-туннель: процесс умер (код %d), перезапускаю...",
                           _ssh_tunnel_proc.returncode)
            _ssh_tunnel_proc = _start_ssh_tunnel()
            if _ssh_tunnel_proc:
                logger.info("SSH-туннель: перезапущен успешно")
            else:
                logger.error("SSH-туннель: перезапуск не удался")
            continue

        # Проверка 2: порт отвечает?
        try:
            with socket.create_connection(("127.0.0.1", local_port), timeout=2.0):
                pass
        except OSError:
            logger.warning("SSH-туннель: процесс жив, но порт %d не отвечает, "
                           "перезапускаю...", local_port)
            _ssh_tunnel_proc.terminate()
            _ssh_tunnel_proc = _start_ssh_tunnel()


async def main():
    """Main function to start the bot."""
    global _ssh_tunnel_proc
    logger.info("Starting МЭШ School Bot...")

    # SSH-туннель для прокси (если настроен)
    ssh_tunnel = _start_ssh_tunnel()
    _ssh_tunnel_proc = ssh_tunnel

    # Фоновый мониторинг SSH-туннеля (запускаем всегда, если SSH настроен —
    # монитор сам попробует поднять туннель, если первый запуск не удался)
    if getattr(settings, "MESH_SSH_PROXY", False):
        asyncio.create_task(_monitor_ssh_tunnel())

    # Initialize database
    logger.info(f"Initializing database at {settings.DATABASE_PATH}")
    db = await database.init_database(settings.DATABASE_PATH)
    database.db = db  # Set global instance

    # Initialize bot and dispatcher (with proxy if configured)
    bot_session = AiohttpSession(proxy=settings.MESH_PROXY_URL) if settings.MESH_PROXY_URL else None
    if bot_session:
        logger.info("Bot session: using proxy %s", settings.MESH_PROXY_URL)
    bot = Bot(token=settings.BOT_TOKEN, session=bot_session)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Access control middleware (проверка ролей)
    dp.message.middleware(AccessControlMiddleware())
    dp.callback_query.middleware(AccessControlMiddleware())

    # Register routers
    dp.include_router(start.router)
    dp.include_router(registration.router)
    dp.include_router(schedule.router)
    dp.include_router(admin.router)
    dp.include_router(language.router)
    dp.include_router(topic.router)
    dp.include_router(quiz_settings.router)
    dp.include_router(quiz.router)
    dp.include_router(history.router)

    logger.info("Bot handlers registered successfully")

    # Регистрируем команды для меню Telegram
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="raspisanie", description="Расписание уроков"),
        BotCommand(command="ocenki", description="Оценки"),
        BotCommand(command="dz", description="Домашние задания"),
        BotCommand(command="allow", description="Добавить пользователя (админ)"),
        BotCommand(command="block", description="Заблокировать (админ)"),
        BotCommand(command="users", description="Список пользователей (админ)"),
        BotCommand(command="help", description="Справка"),
    ])
    logger.info("Bot menu commands registered")

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
        if _ssh_tunnel_proc:
            _ssh_tunnel_proc.kill()
            _ssh_tunnel_proc.wait(timeout=5)
            logger.info("SSH-туннель: закрыт")
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
