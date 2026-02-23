"""Thread-safe TTL cache utilities (Phase 7.7).

Provides two complementary APIs:

- ``TTLCache``:  Dict-like container with per-entry time-to-live expiry.
- ``ttl_cache``: Decorator that wraps a callable with TTL-based memoisation,
  similar to ``functools.lru_cache`` but with automatic expiry.

Both are thread-safe and suitable for use as class-level shared caches.
"""

from __future__ import annotations

import threading
import time
from collections import namedtuple
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

CacheInfo = namedtuple("CacheInfo", ["hits", "misses", "maxsize", "currsize"])

_SENTINEL = object()
F = TypeVar("F", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# TTLCache — dict-like container
# ---------------------------------------------------------------------------


class TTLCache:
    """Thread-safe key→value store where entries auto-expire.

    Args:
        ttl_seconds: Time-to-live in seconds for each entry.
        maxsize: Optional maximum number of entries.  When exceeded,
            expired entries are evicted first, then the oldest entry.

    Example::

        cache = TTLCache(ttl_seconds=30.0)
        cache.set("cameras", [{"index": 0}])
        result = cache.get("cameras")  # returns list or None
        cache.clear()

    """

    __slots__ = ("_hits", "_lock", "_maxsize", "_misses", "_store", "_ttl")

    def __init__(
        self,
        ttl_seconds: float = 30.0,
        maxsize: int | None = None,
    ) -> None:
        self._ttl = ttl_seconds
        self._maxsize = maxsize
        # key → (value, timestamp)
        self._store: dict[Any, tuple[Any, float]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    # -- public API ---------------------------------------------------------

    @property
    def ttl_seconds(self) -> float:
        """Current TTL value (read-only)."""
        return self._ttl

    @ttl_seconds.setter
    def ttl_seconds(self, value: float) -> None:
        """Allow runtime TTL adjustment (e.g. in tests)."""
        self._ttl = value

    def get(self, key: Any, default: Any = None) -> Any:
        """Return cached value for *key*, or *default* if missing/expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is not None:
                value, ts = entry
                if (time.time() - ts) < self._ttl:
                    self._hits += 1
                    return value
                # Expired — remove lazily
                del self._store[key]
            self._misses += 1
            return default

    def set(self, key: Any, value: Any) -> None:
        """Store *value* under *key* with the current timestamp."""
        now = time.time()
        with self._lock:
            self._store[key] = (value, now)
            self._evict_if_needed(now)

    def invalidate(self, key: Any) -> None:
        """Remove a single entry by *key* (no-op if absent)."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Remove all entries and reset hit/miss counters."""
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def info(self) -> CacheInfo:
        """Return ``CacheInfo(hits, misses, maxsize, currsize)``."""
        with self._lock:
            return CacheInfo(
                self._hits,
                self._misses,
                self._maxsize,
                len(self._store),
            )

    # -- dunder helpers -----------------------------------------------------

    def __contains__(self, key: Any) -> bool:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False
            _, ts = entry
            if (time.time() - ts) < self._ttl:
                return True
            del self._store[key]
            return False

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def __repr__(self) -> str:
        with self._lock:
            currsize = len(self._store)
            ttl_seconds = self._ttl
            maxsize = self._maxsize
        return f"TTLCache(ttl_seconds={ttl_seconds}, maxsize={maxsize}, currsize={currsize})"

    # -- internal -----------------------------------------------------------

    def _evict_if_needed(self, now: float) -> None:
        """Remove expired + over-cap entries (caller holds lock)."""
        # Purge expired
        expired = [k for k, (_, ts) in self._store.items() if (now - ts) >= self._ttl]
        for k in expired:
            del self._store[k]
        # Evict oldest until within maxsize
        if self._maxsize is not None:
            while len(self._store) > self._maxsize:
                oldest = min(self._store, key=lambda k: self._store[k][1])
                del self._store[oldest]


# ---------------------------------------------------------------------------
# ttl_cache — decorator
# ---------------------------------------------------------------------------


def ttl_cache(
    ttl_seconds: float = 30.0,
    maxsize: int | None = 128,
) -> Callable[[F], F]:
    """Decorator: memoises a callable with TTL-based expiry.

    Behaves like ``functools.lru_cache`` but entries expire after
    *ttl_seconds*.  Thread-safe.

    The decorated function gains:

    - ``.cache_clear()`` — purge all entries and reset stats.
    - ``.cache_info()`` — ``CacheInfo(hits, misses, maxsize, currsize)``.
    - ``._cache``       — direct access to the underlying ``TTLCache``
      (useful in tests to inspect or manipulate).

    Example::

        @ttl_cache(ttl_seconds=60)
        def expensive_call(path: str) -> dict:
            ...

        expensive_call("/tmp/foo")   # computes
        expensive_call("/tmp/foo")   # cache hit
        expensive_call.cache_clear() # manual invalidation

    """

    def decorator(func: F) -> F:
        _cache = TTLCache(ttl_seconds=ttl_seconds, maxsize=maxsize)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = args + tuple(sorted(kwargs.items()))
            result = _cache.get(key, _SENTINEL)
            if result is not _SENTINEL:
                return result
            result = func(*args, **kwargs)
            _cache.set(key, result)
            return result

        wrapper.cache_clear = _cache.clear  # type: ignore[attr-defined]
        wrapper.cache_info = _cache.info  # type: ignore[attr-defined]
        wrapper._cache = _cache  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
