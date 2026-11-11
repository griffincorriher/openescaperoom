from __future__ import annotations

import ipaddress
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit


def get_client_ip(
    remote_address: str | None,
    forwarded_for: str | None,
    trusted_proxies: tuple[str, ...],
) -> str:
    """Use X-Forwarded-For only when the immediate peer is a configured proxy."""
    if not remote_address:
        return "unknown"
    try:
        peer = ipaddress.ip_address(remote_address)
    except ValueError:
        return remote_address

    try:
        proxy_networks = tuple(ipaddress.ip_network(value, strict=False) for value in trusted_proxies)
    except ValueError:
        return str(peer)
    if not any(peer in network for network in proxy_networks) or not forwarded_for:
        return str(peer)

    try:
        chain = [ipaddress.ip_address(value.strip()) for value in forwarded_for.split(",")]
    except ValueError:
        return str(peer)

    current = peer
    for candidate in reversed(chain):
        if not any(current in network for network in proxy_networks):
            break
        current = candidate
    return str(current)


def _normalize_origin(origin: str) -> tuple[str, str, int | None] | None:
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    normalized_port = port
    if (parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443):
        normalized_port = None
    return parsed.scheme, parsed.hostname.lower(), normalized_port


def origin_is_allowed(
    origin: str | None,
    request_host: str | None,
    allowed_origins: tuple[str, ...],
) -> bool:
    if not origin or not request_host:
        return False
    origin_parts = _normalize_origin(origin)
    if origin_parts is None:
        return False

    request_parts = _normalize_origin(f"http://{request_host}")
    if request_parts is None:
        request_parts = _normalize_origin(f"https://{request_host}")
    same_host = request_parts is not None and origin_parts[1:] == request_parts[1:]
    return same_host or any(
        origin_parts == _normalize_origin(allowed) for allowed in allowed_origins
    )


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._checks = 0

    def allow(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: float,
        now: float | None = None,
    ) -> bool:
        current_time = time.monotonic() if now is None else now
        events = self._events[key]
        cutoff = current_time - window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            self._events.pop(key, None)
            events = self._events[key]
        if len(events) >= limit:
            return False
        events.append(current_time)
        self._checks += 1
        if self._checks % 256 == 0:
            expired_keys = [
                stored_key
                for stored_key, stored_events in self._events.items()
                if not stored_events or stored_events[-1] <= cutoff
            ]
            for stored_key in expired_keys:
                self._events.pop(stored_key, None)
        return True


class ConnectionLimiter:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def acquire(self, client_ip: str, *, limit: int, replacing_ip: str | None = None) -> bool:
        active = self._counts.get(client_ip, 0)
        if replacing_ip == client_ip:
            active -= 1
        if active >= limit:
            return False
        self._counts[client_ip] = self._counts.get(client_ip, 0) + 1
        return True

    def release(self, client_ip: str) -> None:
        count = self._counts.get(client_ip, 0)
        if count <= 1:
            self._counts.pop(client_ip, None)
        else:
            self._counts[client_ip] = count - 1
