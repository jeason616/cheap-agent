import hashlib
import time
from typing import Any

# Default TTL (seconds) when set_cache is called without an explicit ttl_sec.
# Matches the historical hardcoded expiry so behavior is unchanged for callers
# that relied on the old 300s constant.
DEFAULT_TTL_SEC = 300

_cache: dict[str, tuple[float, Any, float]] = {}


def make_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


def get_cache(key: str) -> Any | None:
    if key not in _cache:
        return None
    ts, value, ttl = _cache[key]
    if time.monotonic() - ts > ttl:
        del _cache[key]
        return None
    return value


def set_cache(key: str, value: Any, ttl_sec: int | None = None) -> None:
    ttl = ttl_sec if ttl_sec and ttl_sec > 0 else DEFAULT_TTL_SEC
    _cache[key] = (time.monotonic(), value, ttl)


def invalidate_cache(prefix: str = "") -> int:
    if not prefix:
        count = len(_cache)
        _cache.clear()
        return count
    keys = [k for k in _cache if k.startswith(prefix)]
    for k in keys:
        del _cache[k]
    return len(keys)
