import asyncio
import time
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TokenBucket:
    rate: float  # tokens per second
    capacity: float = 0
    _tokens: float = field(init=False, default=0)
    _last_refill: float = field(init=False, default_factory=time.monotonic)
    _lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)

    def __post_init__(self):
        if self.capacity == 0:
            self.capacity = max(1.0, self.rate * 2)
        self._tokens = self.capacity

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._last_refill = now

            if self._tokens < 1.0:
                wait_time = (1.0 - self._tokens) / self.rate
                logger.debug(f"Rate limit: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                self._tokens = 0
            else:
                self._tokens -= 1.0


class RateLimiterRegistry:
    def __init__(self):
        self._limiters: dict[str, TokenBucket] = {}

    def register(self, source: str, rate: float):
        self._limiters[source] = TokenBucket(rate=rate)

    def get(self, source: str) -> TokenBucket | None:
        return self._limiters.get(source)

    async def acquire(self, source: str):
        limiter = self._limiters.get(source)
        if limiter:
            await limiter.acquire()


rate_limiters = RateLimiterRegistry()
