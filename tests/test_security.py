from app.security import (
    ConnectionLimiter,
    SlidingWindowRateLimiter,
    get_client_ip,
    origin_is_allowed,
)


def test_forwarded_ip_is_used_only_for_trusted_proxy():
    trusted = ("10.0.0.0/8",)
    assert get_client_ip("198.51.100.5", "203.0.113.8", trusted) == "198.51.100.5"
    assert get_client_ip("10.0.0.2", "203.0.113.8, 10.0.0.1", trusted) == "203.0.113.8"
    assert get_client_ip("10.0.0.2", "not-an-ip", trusted) == "10.0.0.2"


def test_origin_check_allows_same_host_and_configured_origin_only():
    origins = ("https://games.example.com",)
    assert origin_is_allowed("https://example.test", "example.test", origins)
    assert origin_is_allowed("https://games.example.com", "server.internal", origins)
    assert not origin_is_allowed("https://evil.example", "example.test", origins)
    assert not origin_is_allowed(None, "example.test", origins)


def test_sliding_window_rate_limit():
    limiter = SlidingWindowRateLimiter()
    assert limiter.allow("client", limit=2, window_seconds=1, now=10)
    assert limiter.allow("client", limit=2, window_seconds=1, now=10.5)
    assert not limiter.allow("client", limit=2, window_seconds=1, now=10.75)
    assert limiter.allow("client", limit=2, window_seconds=1, now=11.5)


def test_connection_limit_accounts_for_reconnects():
    limiter = ConnectionLimiter()
    assert limiter.acquire("client", limit=1)
    assert limiter.acquire("client", limit=1, replacing_ip="client")
    assert not limiter.acquire("client", limit=1)
    limiter.release("client")
    limiter.release("client")
    assert limiter.acquire("client", limit=1)
