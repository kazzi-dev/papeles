from starlette.requests import Request

from app.ratelimit import DAY, MINUTE, RateLimiter, visitor_id


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_per_visitor_minute_limit_and_reset():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=2, per_day=0, global_per_minute=0, clock=clock)

    assert limiter.check("a") is None
    assert limiter.check("a") is None
    assert limiter.check("a") == MINUTE  # third in the same minute is blocked
    assert limiter.check("b") is None  # other visitors are unaffected

    clock.now += MINUTE
    assert limiter.check("a") is None


def test_daily_limit():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=0, per_day=3, global_per_minute=0, clock=clock)
    for _ in range(3):
        assert limiter.check("a") is None
        clock.now += MINUTE
    assert limiter.check("a") is not None
    clock.now += DAY
    assert limiter.check("a") is None


def test_global_limit_applies_across_visitors():
    limiter = RateLimiter(per_minute=0, per_day=0, global_per_minute=2, clock=FakeClock())
    assert limiter.check("a") is None
    assert limiter.check("b") is None
    assert limiter.check("c") is not None


def test_blocked_requests_do_not_use_up_other_limits():
    limiter = RateLimiter(per_minute=1, per_day=0, global_per_minute=2, clock=FakeClock())
    assert limiter.check("a") is None
    assert limiter.check("a") is not None  # blocked by the per-visitor limit...
    assert limiter.check("b") is None  # ...so it didn't count toward the global one


def test_zero_disables_all_limits():
    limiter = RateLimiter(0, 0, 0, clock=FakeClock())
    assert all(limiter.check("a") is None for _ in range(100))


def request_with(headers: dict[str, str], host: str = "10.0.0.1") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (host, 1234)})


def test_visitor_id_uses_last_forwarded_address_behind_proxy():
    req = request_with({"X-Forwarded-For": "1.1.1.1, 203.0.113.7"})
    assert visitor_id(req) == "203.0.113.7"


def test_visitor_id_falls_back_to_client_address():
    assert visitor_id(request_with({})) == "10.0.0.1"
