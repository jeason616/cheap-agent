import hashlib
import time
from typing import Any

_cache: dict[str, tuple[float, Any]] = {}


def make_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


def get_cache(key: str) -> Any | None:
    if key not in _cache:
        return None
    ts, value = _cache[key]
    if time.monotonic() - ts > 300:
        del _cache[key]
        return None
    return value


def set_cache(key: str, value: Any, ttl_sec: int | None = None) -> None:
    _cache[key] = (time.monotonic(), value)


def invalidate_cache(prefix: str = "") -> int:
    if not prefix:
        count = len(_cache)
        _cache.clear()
        return count
    keys = [k for k in _cache if k.startswith(prefix)]
    for k in keys:
        del _cache[k]
    return len(keys)
