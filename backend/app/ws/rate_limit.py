import time
from collections.abc import Callable


class TokenBucket:
    """Balde de fichas: começa cheio, repõe `rate` fichas por segundo até `burst`."""

    def __init__(
        self, rate: float, burst: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._rate = rate
        self._burst = burst
        self._clock = clock
        self._tokens = float(burst)
        self._updated_at = clock()

    def allow(self) -> bool:
        now = self._clock()
        elapsed = now - self._updated_at
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._updated_at = now
        if self._tokens < 1:
            return False
        self._tokens -= 1
        return True
