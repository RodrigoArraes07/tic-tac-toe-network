from app.ws.rate_limit import TokenBucket

RATE_PER_SECOND = 2.0
BURST = 3


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_bucket_allows_the_burst_then_refills_over_time() -> None:
    clock = FakeClock()
    bucket = TokenBucket(RATE_PER_SECOND, BURST, clock=clock)

    burst = [bucket.allow() for _ in range(BURST)]
    over_limit = bucket.allow()
    clock.now += 1 / RATE_PER_SECOND
    after_one_token = bucket.allow()
    still_empty = bucket.allow()

    assert burst == [True] * BURST
    assert over_limit is False
    assert after_one_token is True
    assert still_empty is False


def test_bucket_never_holds_more_than_the_burst() -> None:
    clock = FakeClock()
    bucket = TokenBucket(RATE_PER_SECOND, BURST, clock=clock)
    clock.now += 60

    allowed = [bucket.allow() for _ in range(BURST + 1)]

    assert allowed == [True] * BURST + [False]
