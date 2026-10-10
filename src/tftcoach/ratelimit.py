"""Client-side sliding-window rate limiter, shared by the Riot and LLM clients."""

import time
from collections import deque
from collections.abc import Callable

# Development and personal keys: 20 requests per second and 100 per 2 minutes.
DEV_KEY_LIMITS: tuple[tuple[int, float], ...] = ((20, 1.0), (100, 120.0))


class RateLimiter:
    """Blocks in `acquire()` until a request fits inside every (max_requests, window) limit."""

    def __init__(
        self,
        limits: tuple[tuple[int, float], ...] = DEV_KEY_LIMITS,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._limits = limits
        self._clock = clock
        self._sleep = sleep
        # Timestamps of recent requests; long enough to cover the widest window.
        self._history: deque[float] = deque()

    def acquire(self) -> None:
        while True:
            now = self._clock()
            longest_window = max(window for _, window in self._limits)
            while self._history and now - self._history[0] >= longest_window:
                self._history.popleft()

            wait = 0.0
            for max_requests, window in self._limits:
                in_window = [t for t in self._history if now - t < window]
                if len(in_window) >= max_requests:
                    # Wait until the oldest request in this window ages out.
                    wait = max(wait, in_window[-max_requests] + window - now)
            if wait <= 0:
                self._history.append(now)
                return
            self._sleep(wait)
