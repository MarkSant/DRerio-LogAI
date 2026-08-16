"""Extended unit tests for utils/cache.py."""

from __future__ import annotations

import time
from typing import Any, cast

from zebtrack.utils.cache import TTLCache, ttl_cache


class TestTTLCacheExtended:
    """Test TTLCache operations, TTL expiration, maxsize eviction,
    hit/miss counting, and dunders.
    """

    def test_cache_get_and_set(self):
        cache = TTLCache(ttl_seconds=10.0)
        cache.set("key1", "val1")
        assert cache.get("key1") == "val1"
        assert cache.get("missing", default="def") == "def"

    def test_cache_expiration(self):
        cache = TTLCache(ttl_seconds=0.05)
        cache.set("key1", "val1")
        assert cache.get("key1") == "val1"

        time.sleep(0.06)
        assert cache.get("key1") is None
        assert "key1" not in cache

    def test_cache_invalidate_and_clear(self):
        cache = TTLCache(ttl_seconds=10.0)
        cache.set("a", 1)
        cache.set("b", 2)

        cache.invalidate("a")
        assert cache.get("a") is None
        assert cache.get("b") == 2

        cache.clear()
        assert len(cache) == 0
        info = cache.info()
        assert info.hits == 0
        assert info.misses == 0
        assert info.currsize == 0

    def test_cache_maxsize_eviction(self):
        cache = TTLCache(ttl_seconds=10.0, maxsize=2)
        cache.set("k1", 1)
        time.sleep(0.01)
        cache.set("k2", 2)
        time.sleep(0.01)
        cache.set("k3", 3)

        assert len(cache) <= 2
        # Oldest entry k1 should have been evicted
        assert cache.get("k1") is None
        assert cache.get("k2") == 2
        assert cache.get("k3") == 3

    def test_cache_contains_and_len(self):
        cache = TTLCache(ttl_seconds=10.0)
        cache.set("x", 100)
        assert "x" in cache
        assert "y" not in cache
        assert len(cache) == 1

    def test_cache_repr(self):
        cache = TTLCache(ttl_seconds=15.0, maxsize=50)
        r = repr(cache)
        assert "TTLCache" in r
        assert "ttl_seconds=15.0" in r
        assert "maxsize=50" in r

    def test_cache_ttl_setter(self):
        cache = TTLCache(ttl_seconds=5.0)
        assert cache.ttl_seconds == 5.0
        cache.ttl_seconds = 20.0
        assert cache.ttl_seconds == 20.0


class TestTTLCacheDecoratorExtended:
    """Test ttl_cache decorator behavior, memoization, and cache control helpers."""

    def test_ttl_cache_decorator(self):
        call_count = 0

        @ttl_cache(ttl_seconds=10.0)
        def compute_square(n: int) -> int:
            nonlocal call_count
            call_count += 1
            return n * n

        assert compute_square(4) == 16
        assert call_count == 1

        # Second call hits cache
        assert compute_square(4) == 16
        assert call_count == 1

        # Call with different arg computes
        assert compute_square(5) == 25
        assert call_count == 2

        # Cache info
        func_any = cast(Any, compute_square)
        info = func_any.cache_info()
        assert info.hits == 1
        assert info.misses == 2

        # Cache clear
        func_any.cache_clear()
        assert compute_square(4) == 16
        assert call_count == 3
