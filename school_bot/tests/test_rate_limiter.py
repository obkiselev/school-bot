"""Тесты TokenBucketRateLimiter."""
import asyncio
import pytest
from unittest.mock import patch, AsyncMock


class TestTokenBucketRateLimiter:
    """Тесты rate limiter — token bucket алгоритм."""

    def _make_limiter(self, max_calls=5, period=60.0):
        from utils.rate_limiter import TokenBucketRateLimiter
        return TokenBucketRateLimiter(max_calls=max_calls, period_seconds=period)

    async def test_acquire_immediate(self):
        """Первый acquire проходит сразу."""
        limiter = self._make_limiter()
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await limiter.acquire()
            mock_sleep.assert_not_called()

    async def test_burst_allowed(self):
        """N быстрых acquire проходят без задержки."""
        limiter = self._make_limiter(max_calls=5)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            for _ in range(5):
                await limiter.acquire()
            mock_sleep.assert_not_called()

    async def test_sleep_when_exhausted(self):
        """После исчерпания токенов — вызывается asyncio.sleep."""
        limiter = self._make_limiter(max_calls=2, period=60.0)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await limiter.acquire()
            await limiter.acquire()
            # 3rd call should sleep
            await limiter.acquire()
            mock_sleep.assert_called_once()
            sleep_time = mock_sleep.call_args[0][0]
            assert sleep_time > 0

    async def test_refill_over_time(self):
        """Токены восстанавливаются с течением времени."""
        limiter = self._make_limiter(max_calls=2, period=60.0)

        # Exhaust tokens
        await limiter.acquire()
        await limiter.acquire()

        # Advance time by full period
        with patch("time.monotonic", return_value=limiter._last_refill + 60.0):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await limiter.acquire()
                mock_sleep.assert_not_called()

    async def test_tokens_capped_at_max(self):
        """Токены не превышают max_calls даже после долгого ожидания."""
        limiter = self._make_limiter(max_calls=3, period=60.0)

        # Advance time by 10 periods
        with patch("time.monotonic", return_value=limiter._last_refill + 600.0):
            limiter._refill()
            assert limiter._tokens == 3.0  # capped

    async def test_concurrent_access(self):
        """Несколько параллельных acquire не вызывают ошибок."""
        limiter = self._make_limiter(max_calls=10, period=60.0)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            results = await asyncio.gather(
                limiter.acquire(),
                limiter.acquire(),
                limiter.acquire(),
            )
            assert len(results) == 3
