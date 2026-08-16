"""
Extended unit tests for TTLCache and ttl_cache decorator in utils/cache.py.
"""

from __future__ import annotations

import time

from zebtrack.utils.cache import TTLCache, ttl_cache


class TestTTLCacheExtended:
    """Test TTLCache edge cases and decorator features."""

    def test_decorator_kwargs_and_cache_attribute(self):
        call_count = 0

        @ttl_cache(ttl_seconds=5.0)
        def query(a: int, b: str = "default") -> str:
            nonlocal call_count
            call_count += 1
            return f"{a}:{b}"

        assert query(1, b="x") == "1:x"
        assert query(1, b="x") == "1:x"  # Hit
        assert call_count == 1

        # Direct access to _cache
        assert query._cache.info().hits == 1  # type: ignore[attr-defined]
        assert query._cache.info().misses == 1  # type: ignore[attr-defined]

    def test_evict_expired_during_set(self):
        cache = TTLCache(ttl_seconds=0.04, maxsize=10)
        cache.set("a", 1)
        cache.set("b", 2)
        time.sleep(0.06)
        # Setting 'c' will trigger _evict_if_needed, removing expired 'a' and 'b'
        cache.set("c", 3)
        assert len(cache) == 1
        assert "a" not in cache
        assert "b" not in cache
        assert cache.get("c") == 3
