"""Extended unit tests for utils/cache.py."""

from __future__ import annotations

import time

from zebtrack.utils.cache import TTLCache, ttl_cache


class TestCacheExtended2:
    """Test thread-safe TTLCache and ttl_cache decorator."""

    def test_ttl_cache_hit_and_miss(self):
        cache = TTLCache(ttl_seconds=10.0, maxsize=5)
        assert cache.get("key1") is None
        assert cache.get("key1", default="default_val") == "default_val"

        cache.set("key1", "val1")
        assert cache.get("key1") == "val1"
        assert len(cache._store) == 1
        assert cache._hits == 1
        assert cache._misses == 2

    def test_ttl_cache_expiration(self):
        cache = TTLCache(ttl_seconds=0.01)
        cache.set("ephemeral", 12345)
        time.sleep(0.02)
        assert cache.get("ephemeral") is None

    def test_ttl_cache_invalidate_and_clear(self):
        cache = TTLCache(ttl_seconds=60.0)
        cache.set("k1", 1)
        cache.set("k2", 2)

        cache.invalidate("k1")
        assert cache.get("k1") is None
        assert cache.get("k2") == 2

        cache.clear()
        assert cache.get("k2") is None
        assert len(cache._store) == 0

    def test_ttl_cache_decorator(self):
        call_count = 0

        @ttl_cache(ttl_seconds=5.0)
        def expensive_calc(a: int, b: int) -> int:
            nonlocal call_count
            call_count += 1
            return a + b

        assert expensive_calc(2, 3) == 5
        assert call_count == 1

        # Second call should be cached
        assert expensive_calc(2, 3) == 5
        assert call_count == 1

        # Different arguments
        assert expensive_calc(5, 5) == 10
        assert call_count == 2

        info = expensive_calc.cache_info()  # type: ignore[attr-defined]
        assert info.hits == 1
        assert info.misses == 2
