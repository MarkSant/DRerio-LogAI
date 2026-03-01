"""Tests for TTLCache and ttl_cache utilities (Phase 7.7)."""

from __future__ import annotations

import time

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
