from tftcoach.ratelimit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_allows_burst_up_to_limit_without_waiting() -> None:
    clock = FakeClock()
    limiter = RateLimiter(((3, 1.0),), clock=clock, sleep=clock.sleep)
    for _ in range(3):
        limiter.acquire()
    assert clock.sleeps == []


def test_waits_for_oldest_request_to_leave_window() -> None:
    clock = FakeClock()
    limiter = RateLimiter(((3, 1.0),), clock=clock, sleep=clock.sleep)
    for _ in range(3):
        limiter.acquire()
        clock.now += 0.25  # requests at t=0, 0.25, 0.5
    limiter.acquire()  # t=0.75: must wait until t=1.0
    assert clock.sleeps == [0.25]


def test_respects_the_longer_window() -> None:
    clock = FakeClock()
    limiter = RateLimiter(((20, 1.0), (5, 120.0)), clock=clock, sleep=clock.sleep)
    for _ in range(5):
        limiter.acquire()
    limiter.acquire()
    assert clock.sleeps == [120.0]
