"""Tests for the in-memory cache layer (cheap_agent.cache).

This module previously had zero test coverage. Covers the get/set round
trip, TTL expiry (now honoring the ttl_sec argument — previously ignored),
invalidate_cache prefix + full clear, and make_hash stability.
"""

from cheap_agent.cache import (
    DEFAULT_TTL_SEC,
    _cache,
    get_cache,
    invalidate_cache,
    make_hash,
    set_cache,
)


def setup_function():
    _cache.clear()


def test_set_get_roundtrip():
    set_cache("k1", {"a": 1})
    assert get_cache("k1") == {"a": 1}


def test_get_missing_returns_none():
    assert get_cache("nope") is None


def test_set_overwrites():
    set_cache("k", "v1")
    set_cache("k", "v2")
    assert get_cache("k") == "v2"


def test_make_hash_stability():
    assert make_hash("hello") == make_hash("hello")
    assert make_hash("hello") != make_hash("world")
    assert len(make_hash("x")) == 12


def test_ttl_expired(monkeypatch):
    """A custom short ttl should expire the entry."""
    set_cache("short", "v", ttl_sec=1)
    # Fast-forward the stored timestamp into the past beyond ttl.
    ts, value, ttl = _cache["short"]
    _cache["short"] = (ts - 2, value, ttl)
    assert get_cache("short") is None
    # Expired entry should be evicted from the dict.
    assert "short" not in _cache


def test_ttl_not_yet_expired(monkeypatch):
    set_cache("fresh", "v", ttl_sec=100)
    assert get_cache("fresh") == "v"


def test_ttl_argument_is_honored():
    """Regression: set_cache used to ignore ttl_sec entirely (hardcoded 300
    in get_cache). Now a short ttl should expire faster than the default."""
    set_cache("a", "v", ttl_sec=5)
    set_cache("b", "v", ttl_sec=500)
    _, _, ttl_a = _cache["a"]
    _, _, ttl_b = _cache["b"]
    assert ttl_a == 5
    assert ttl_b == 500


def test_default_ttl_when_none():
    set_cache("k", "v")  # no ttl_sec
    _, _, ttl = _cache["k"]
    assert ttl == DEFAULT_TTL_SEC


def test_invalidate_by_prefix():
    set_cache("ns1:k1", "v")
    set_cache("ns1:k2", "v")
    set_cache("ns2:k1", "v")
    removed = invalidate_cache("ns1:")
    assert removed == 2
    assert get_cache("ns1:k1") is None
    assert get_cache("ns1:k2") is None
    assert get_cache("ns2:k1") == "v"


def test_invalidate_all():
    set_cache("a", 1)
    set_cache("b", 2)
    removed = invalidate_cache()
    assert removed == 2
    assert get_cache("a") is None
    assert get_cache("b") is None


def test_invalidate_prefix_no_match():
    set_cache("keep", "v")
    removed = invalidate_cache("nonexistent:")
    assert removed == 0
    assert get_cache("keep") == "v"
