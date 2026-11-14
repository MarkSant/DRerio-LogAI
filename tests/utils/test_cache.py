"""Tests for TTLCache and ttl_cache utilities (Phase 7.7)."""

from __future__ import annotations

import time
from typing import Any, cast

from zebtrack.utils.cache import TTLCache, ttl_cache


class TestTTLCache:
    """Test the TTLCache dict-like container."""

    def test_get_set_basic(self):
        cache = TTLCache(ttl_seconds=10.0)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_returns_default(self):
        cache = TTLCache(ttl_seconds=10.0)
        assert cache.get("missing") is None
        assert cache.get("missing", "fallback") == "fallback"

    def test_entry_expires_after_ttl(self):
        cache = TTLCache(ttl_seconds=0.05)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        time.sleep(0.08)
        assert cache.get("key1") is None

    def test_invalidate_removes_entry(self):
        cache = TTLCache(ttl_seconds=10.0)
        cache.set("key1", "value1")
        cache.invalidate("key1")
        assert cache.get("key1") is None

    def test_invalidate_missing_key_no_error(self):
        cache = TTLCache(ttl_seconds=10.0)
        cache.invalidate("nope")  # should not raise

    def test_clear_removes_all_entries(self):
        cache = TTLCache(ttl_seconds=10.0)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_contains(self):
        cache = TTLCache(ttl_seconds=10.0)
        cache.set("key1", "value1")
        assert "key1" in cache
        assert "key2" not in cache

    def test_contains_expired(self):
        cache = TTLCache(ttl_seconds=0.05)
        cache.set("key1", "value1")
        time.sleep(0.08)
        assert "key1" not in cache

    def test_len(self):
        cache = TTLCache(ttl_seconds=10.0)
        assert len(cache) == 0
        cache.set("a", 1)
        cache.set("b", 2)
        assert len(cache) == 2

    def test_info_tracks_hits_misses(self):
        cache = TTLCache(ttl_seconds=10.0)
        cache.set("a", 1)
        cache.get("a")  # hit
        cache.get("a")  # hit
        cache.get("b")  # miss
        info = cache.info()
        assert info.hits == 2
        assert info.misses == 1
        assert info.currsize == 1

    def test_maxsize_eviction(self):
        cache = TTLCache(ttl_seconds=10.0, maxsize=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # should evict oldest
        assert len(cache) <= 2
        assert cache.get("c") == 3

    def test_ttl_seconds_property(self):
        cache = TTLCache(ttl_seconds=30.0)
        assert cache.ttl_seconds == 30.0
        cache.ttl_seconds = 5.0
        assert cache.ttl_seconds == 5.0

    def test_clear_resets_counters(self):
        cache = TTLCache(ttl_seconds=10.0)
        cache.set("key", "val")
        cache.get("key")  # hit
        cache.get("miss")  # miss
        cache.clear()
        info = cache.info()
        assert info.hits == 0
        assert info.misses == 0
        assert info.currsize == 0

    def test_repr(self):
        cache = TTLCache(ttl_seconds=30.0, maxsize=10)
        text = repr(cache)
        assert "TTLCache" in text
        assert "30.0" in text


class TestTTLCacheDecorator:
    """Test the ttl_cache function decorator."""

    def test_basic_memoisation(self):
        call_count = 0

        @ttl_cache(ttl_seconds=10.0)
        def expensive(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        assert expensive(5) == 10
        assert expensive(5) == 10  # cached
        assert call_count == 1

    def test_different_args_different_entries(self):
        call_count = 0

        @ttl_cache(ttl_seconds=10.0)
        def add(a: int, b: int) -> int:
            nonlocal call_count
            call_count += 1
            return a + b

        assert add(1, 2) == 3
        assert add(3, 4) == 7
        assert call_count == 2
        assert add(1, 2) == 3  # cached
        assert call_count == 2

    def test_cache_expires(self):
        call_count = 0

        @ttl_cache(ttl_seconds=0.05)
        def compute(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x

        assert compute(1) == 1
        assert call_count == 1

        time.sleep(0.08)

        assert compute(1) == 1
        assert call_count == 2  # recomputed

    def test_cache_clear(self):
        call_count = 0

        @ttl_cache(ttl_seconds=10.0)
        def compute(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x

        compute(1)
        compute.cache_clear()  # type: ignore[attr-defined]
        compute(1)
        assert call_count == 2

    def test_cache_info(self):
        @ttl_cache(ttl_seconds=10.0, maxsize=5)
        def compute(x: int) -> int:
            return x

        compute(1)
        compute(1)  # hit
        compute(2)

        info = compute.cache_info()  # type: ignore[attr-defined]
        assert info.hits == 1
        assert info.misses == 2
        assert info.currsize == 2
        assert info.maxsize == 5

    def test_preserves_function_metadata(self):
        @ttl_cache(ttl_seconds=10.0)
        def my_function():
            """My docstring."""

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."


class TestTTLCacheExtended:
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


class TestCacheExtended2:
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
