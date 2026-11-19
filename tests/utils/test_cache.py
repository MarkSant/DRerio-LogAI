"""Tests for TTLCache and ttl_cache utilities (Phase 7.7)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast
from unittest import mock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

import zebtrack.utils.cache as cache_module
from zebtrack.utils.cache import TTLCache, ttl_cache

_MISSING = object()


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


# ---------------------------------------------------------------------------
# Property-based invariants (hypothesis)
# ---------------------------------------------------------------------------

#: The same examples on every machine: a CI failure must be one a developer can
#: reproduce, never a draw nobody saw locally.
_PROPERTY = settings(max_examples=100, database=None, derandomize=True, deadline=None)

_KEYS = st.sampled_from(["a", "b", "c", "d", "e"])


class _FakeClock:
    """Stands in for the ``time`` module inside ``zebtrack.utils.cache``.

    Whole seconds only, so ``now - written`` is exact and the TTL boundary is
    hit on the dot instead of a rounding error away from it.
    """

    def __init__(self) -> None:
        self.now = 1_000.0
        #: The wall clock, deliberately unrelated to ``now``: expiry must follow
        #: ``monotonic()`` and ignore wherever this one is (NTP step, DST, manual change).
        self.wall = 9_000_000.0

    def monotonic(self) -> float:
        return self.now

    def time(self) -> float:
        return self.wall


@contextmanager
def _frozen_clock() -> Iterator[_FakeClock]:
    clock = _FakeClock()
    with mock.patch.object(cache_module, "time", clock):
        yield clock


class TestTTLCacheProperties:
    @_PROPERTY
    @given(_KEYS, st.integers(), st.integers(1, 60), st.integers(0, 120))
    def test_a_value_is_read_back_exactly_until_its_ttl_runs_out(self, key, value, ttl, elapsed):
        # Two caches, because both ``get`` and ``in`` delete what they find
        # expired: whichever ran first would decide the other's answer.
        with _frozen_clock() as clock:
            read_by_get = TTLCache(ttl_seconds=float(ttl))
            read_by_in = TTLCache(ttl_seconds=float(ttl))
            read_by_get.set(key, value)
            read_by_in.set(key, value)
            clock.now += elapsed
            alive = elapsed < ttl
            assert read_by_get.get(key, _MISSING) == (value if alive else _MISSING)
            assert (key in read_by_in) is alive

    @_PROPERTY
    @given(st.integers(1, 10), st.lists(st.integers(0, 12), min_size=1, max_size=6))
    def test_a_write_purges_every_entry_whose_ttl_has_run_out(self, ttl, ages):
        with _frozen_clock() as clock:
            cache = TTLCache(ttl_seconds=float(ttl))
            now = clock.now + max(ages)
            for index, age in enumerate(sorted(ages, reverse=True)):
                clock.now = now - age
                cache.set(f"written-{index}", index)
            clock.now = now

            cache.set("fresh", -1)

            # ``len`` does not purge, so it shows exactly what the write kept.
            assert len(cache) == 1 + sum(age < ttl for age in ages)

    @_PROPERTY
    @given(st.lists(_KEYS, min_size=1, max_size=30), st.integers(0, 4), st.booleans())
    def test_the_cap_keeps_exactly_the_most_recently_written_keys(
        self, writes, maxsize, clock_ticks
    ):
        # With a clock that does not move between writes (a coarse timer), every
        # entry has the same timestamp and "oldest" must mean "written first".
        with _frozen_clock() as clock:
            cache = TTLCache(ttl_seconds=1e9, maxsize=maxsize)
            for index, key in enumerate(writes):
                if clock_ticks:
                    clock.now += 1
                cache.set(key, index)
                assert len(cache) <= maxsize

            newest_first = list(dict.fromkeys(reversed(writes)))
            survivors = newest_first[:maxsize]
            last_write = {key: index for index, key in enumerate(writes)}
            for key in newest_first:
                expected = last_write[key] if key in survivors else _MISSING
                assert cache.get(key, _MISSING) == expected

    def test_rewriting_a_key_makes_it_the_newest_entry_for_eviction(self):
        with _frozen_clock():
            cache = TTLCache(ttl_seconds=60.0, maxsize=2)
            cache.set("a", 1)
            cache.set("b", 2)
            cache.set("a", 3)  # same tick: only the write order tells them apart
            cache.set("c", 4)

            assert cache.get("b") is None
            assert cache.get("a") == 3
            assert cache.get("c") == 4

    @_PROPERTY
    @given(st.dictionaries(_KEYS, st.integers(), min_size=1), st.data())
    def test_invalidating_one_key_leaves_the_others_alone(self, entries, data):
        victim = data.draw(st.sampled_from(sorted(entries)))
        with _frozen_clock():
            cache = TTLCache(ttl_seconds=60.0)
            for key, value in entries.items():
                cache.set(key, value)

            cache.invalidate(victim)

            assert victim not in cache
            for key, value in entries.items():
                if key != victim:
                    assert cache.get(key) == value


_ARG = st.one_of(
    st.integers(-2, 2),
    st.tuples(st.sampled_from(["a", "b"]), st.integers(0, 1)),
)


class TestTTLCacheDecoratorProperties:
    @_PROPERTY
    @given(
        st.lists(
            st.tuples(
                st.lists(_ARG, max_size=1),
                st.dictionaries(st.sampled_from(["a", "b"]), st.integers(0, 1), max_size=1),
            ),
            min_size=1,
            max_size=8,
        )
    )
    def test_every_call_reads_back_its_own_result(self, calls):
        @ttl_cache(ttl_seconds=60.0)
        def echo(*args: Any, **kwargs: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
            return args, kwargs

        for args, kwargs in calls:
            assert echo(*args, **kwargs) == (tuple(args), kwargs)

    def test_a_keyword_argument_never_reads_a_positional_tuples_entry(self):
        # ``f(("a", 1))`` and ``f(a=1)`` used to build the same key, ``(("a", 1),)``.
        @ttl_cache(ttl_seconds=60.0)
        def echo(*args: Any, **kwargs: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
            return args, kwargs

        assert echo(("a", 1)) == ((("a", 1),), {})
        assert echo(a=1) == ((), {"a": 1})


class TTLCacheMachine(RuleBasedStateMachine):
    """``TTLCache`` against a plain dict in write order plus a fake clock."""

    def __init__(self) -> None:
        super().__init__()
        self.clock = _FakeClock()
        self._patch = mock.patch.object(cache_module, "time", self.clock)
        self._patch.start()
        self.ttl = 1
        self.maxsize: int | None = None
        self.cache = TTLCache()
        # key -> (value, written_at), oldest write first
        self.model: dict[str, tuple[int, float]] = {}
        self.hits = 0
        self.misses = 0

    def teardown(self) -> None:
        self._patch.stop()

    def _alive(self, key: str) -> bool:
        return key in self.model and self.clock.now - self.model[key][1] < self.ttl

    @initialize(ttl=st.integers(1, 6), maxsize=st.one_of(st.none(), st.integers(0, 4)))
    def build(self, ttl: int, maxsize: int | None) -> None:
        self.ttl = ttl
        self.maxsize = maxsize
        self.cache = TTLCache(ttl_seconds=float(ttl), maxsize=maxsize)

    @rule(seconds=st.integers(0, 4))
    def tick(self, seconds: int) -> None:
        self.clock.now += seconds

    @rule(key=_KEYS, value=st.integers())
    def set(self, key: str, value: int) -> None:
        self.cache.set(key, value)
        self.model.pop(key, None)
        self.model[key] = (value, self.clock.now)
        for stale in [k for k in self.model if not self._alive(k)]:
            del self.model[stale]
        while self.maxsize is not None and len(self.model) > self.maxsize:
            del self.model[next(iter(self.model))]

    @rule(key=_KEYS)
    def get(self, key: str) -> None:
        if self._alive(key):
            self.hits += 1
            expected: Any = self.model[key][0]
        else:
            self.misses += 1
            self.model.pop(key, None)
            expected = _MISSING
        assert self.cache.get(key, _MISSING) == expected

    @rule(key=_KEYS)
    def contains(self, key: str) -> None:
        alive = self._alive(key)
        if not alive:
            self.model.pop(key, None)
        assert (key in self.cache) is alive

    @rule(key=_KEYS)
    def invalidate(self, key: str) -> None:
        self.cache.invalidate(key)
        self.model.pop(key, None)

    @rule()
    def clear(self) -> None:
        self.cache.clear()
        self.model.clear()
        self.hits = 0
        self.misses = 0

    @rule(jump=st.integers(-10_000, 10_000))
    def wall_clock_jumps(self, jump: int) -> None:
        self.clock.wall += jump

    @rule(ttl=st.integers(1, 6))
    def change_ttl(self, ttl: int) -> None:
        self.cache.ttl_seconds = float(ttl)
        self.ttl = ttl

    @invariant()
    def size_and_counters_match_the_model(self) -> None:
        # ``info`` and ``len`` purge what expired, and a purge is permanent: a
        # later TTL increase must not bring the entry back, so the model drops it too.
        for stale in [k for k in self.model if not self._alive(k)]:
            del self.model[stale]
        info = self.cache.info()
        assert info == (self.hits, self.misses, self.maxsize, len(self.model))
        assert len(self.cache) == len(self.model)
        if self.maxsize is not None:
            assert len(self.cache) <= self.maxsize


TestTTLCacheModel = TTLCacheMachine.TestCase


class TestTTLCacheClock:
    """Expiry runs on the monotonic clock, and ``len`` counts only live entries."""

    @pytest.mark.parametrize("jump", [3_600.0, -3_600.0, 86_400.0 * 365])
    def test_a_wall_clock_step_does_not_change_expiry(self, jump):
        with _frozen_clock() as clock:
            cache = TTLCache(ttl_seconds=10.0)
            cache.set("a", 1)
            clock.wall += jump  # NTP step / DST / manual change
            assert cache.get("a") == 1
            assert "a" in cache
            assert len(cache) == 1
            clock.now += 10.0  # the monotonic clock reaches the TTL
            clock.wall -= jump  # and the wall clock moves back to where it was
            assert cache.get("a") is None

    def test_expiry_follows_monotonic_time(self):
        with _frozen_clock() as clock:
            cache = TTLCache(ttl_seconds=5.0)
            cache.set("a", 1)
            clock.now += 4.0
            assert cache.get("a") == 1
            clock.now += 1.0
            assert cache.get("a") is None

    def test_set_stamps_the_entry_with_monotonic_time(self):
        with _frozen_clock() as clock:
            cache = TTLCache(ttl_seconds=5.0, maxsize=2)
            cache.set("old", 1)
            clock.now += 1.0
            cache.set("new", 2)
            clock.wall -= 1_000_000.0  # a wall-clock stamp would make "new" the oldest
            clock.now += 1.0
            cache.set("third", 3)
            assert cache.get("new") == 2
            assert cache.get("old") is None

    def test_len_excludes_expired_entries_without_a_prior_read(self):
        with _frozen_clock() as clock:
            cache = TTLCache(ttl_seconds=5.0)
            cache.set("a", 1)
            clock.now += 3.0
            cache.set("b", 2)
            clock.now += 2.0  # "a" is now exactly at its TTL, "b" is still live
            assert len(cache) == 1
            assert cache.get("b") == 2
            clock.now += 3.0
            assert len(cache) == 0

    def test_decorator_expiry_ignores_the_wall_clock(self):
        calls = []

        with _frozen_clock() as clock:

            @ttl_cache(ttl_seconds=10.0)
            def compute(x):
                calls.append(x)
                return x * 2

            assert compute(2) == 4
            clock.wall += 86_400.0
            assert compute(2) == 4
            assert calls == [2]
            clock.now += 10.0
            assert compute(2) == 4
            assert calls == [2, 2]


TestTTLCacheModel.settings = settings(
    max_examples=60,
    stateful_step_count=30,
    database=None,
    derandomize=True,
    deadline=None,
)
