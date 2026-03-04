"""Global rate limiter for МЭШ API calls (token bucket)."""
import asyncio
import time
import logging

from config import settings

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """
    Async token bucket — ограничивает частоту запросов к МЭШ API.

    Позволяет небольшие всплески (burst), но держит среднюю скорость
    не выше max_calls / period_seconds.
    """

    def __init__(self, max_calls: int, period_seconds: float):
        self._max_calls = max_calls
        self._period = period_seconds
        self._tokens = float(max_calls)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Дождаться свободного токена и забрать его."""
        async with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            # Нет токенов — считаем время ожидания
            wait_time = (1.0 - self._tokens) * (self._period / self._max_calls)

        logger.debug("МЭШ API rate limit: ожидание %.2f сек", wait_time)
        await asyncio.sleep(wait_time)

        async with self._lock:
            self._refill()
            self._tokens = max(0.0, self._tokens - 1.0)

    def _refill(self):
        """Пополнить токены пропорционально прошедшему времени."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        refill = elapsed * (self._max_calls / self._period)
        self._tokens = min(self._max_calls, self._tokens + refill)
        self._last_refill = now


# Единственный экземпляр на весь бот
mesh_api_limiter = TokenBucketRateLimiter(
    max_calls=settings.API_MAX_CALLS,
    period_seconds=settings.API_PERIOD_SECONDS,
)
