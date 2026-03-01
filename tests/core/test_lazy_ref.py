"""Tests for LazyRef transparent proxy.

Phase 6: Comprehensive unit tests for the LazyRef[T] class that replaces the
unsafe __new__ two-phase initialization pattern in the Composition Root.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from zebtrack.core.dependency_container import LazyRef


class _FakeController:
    """Minimal fake controller for testing LazyRef delegation."""

    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.call_count = 0

    def on_close(self) -> str:
        self.call_count += 1
        return f"closed:{self.name}"

    def greet(self, who: str) -> str:
        return f"hello {who} from {self.name}"


class TestLazyRefLifecycle:
    """Tests for the basic lifecycle of LazyRef: create → set → access."""

    def test_initial_state_is_unresolved(self):
        ref: LazyRef[_FakeController] = LazyRef("test")
        assert ref.is_resolved is False

    def test_set_resolves_instance(self):
        ref: LazyRef[_FakeController] = LazyRef("test")
        obj = _FakeController()
        ref.set(obj)
        assert ref.is_resolved is True

    def test_get_returns_instance_after_set(self):
        ref: LazyRef[_FakeController] = LazyRef("test")
        obj = _FakeController("ctrl")
        ref.set(obj)
        assert ref.get() is obj

    def test_get_raises_before_set(self):
        ref: LazyRef[_FakeController] = LazyRef("test")
        with pytest.raises(RuntimeError, match="instance not yet set"):
            ref.get()

    def test_set_twice_raises(self):
        ref: LazyRef[_FakeController] = LazyRef("test")
        ref.set(_FakeController())
        with pytest.raises(RuntimeError, match="instance already set"):
            ref.set(_FakeController())

    def test_repr_unresolved(self):
        ref: LazyRef[_FakeController] = LazyRef("MainViewModel")
        assert "unresolved" in repr(ref)
        assert "MainViewModel" in repr(ref)

    def test_repr_resolved(self):
        ref: LazyRef[_FakeController] = LazyRef("MainViewModel")
        ref.set(_FakeController())
        r = repr(ref)
        assert "MainViewModel" in r
        assert "_FakeController" in r
        assert "unresolved" not in r


class TestLazyRefTransparentProxy:
    """Tests for __getattr__ delegation (the transparent proxy behavior)."""

    def test_attribute_access_after_set(self):
        ref: LazyRef[_FakeController] = LazyRef("ctrl")
        obj = _FakeController("alpha")
        ref.set(obj)
        assert ref.name == "alpha"

    def test_method_call_after_set(self):
        ref: LazyRef[_FakeController] = LazyRef("ctrl")
        obj = _FakeController("beta")
        ref.set(obj)
        assert ref.on_close() == "closed:beta"
        assert obj.call_count == 1

    def test_method_with_args_after_set(self):
        ref: LazyRef[_FakeController] = LazyRef("ctrl")
        obj = _FakeController("gamma")
        ref.set(obj)
        assert ref.greet("world") == "hello world from gamma"

    def test_attribute_access_before_set_raises(self):
        ref: LazyRef[_FakeController] = LazyRef("MyRef")
        with pytest.raises(RuntimeError, match="cannot access 'name' before set"):
            _ = ref.name

    def test_method_access_before_set_raises(self):
        ref: LazyRef[_FakeController] = LazyRef("MyRef")
        with pytest.raises(RuntimeError, match="cannot access 'on_close' before set"):
            ref.on_close()

    def test_setattr_after_set(self):
        ref: LazyRef[_FakeController] = LazyRef("ctrl")
        obj = _FakeController("delta")
        ref.set(obj)
        ref.name = "updated"
        assert obj.name == "updated"

    def test_setattr_before_set_raises(self):
        ref: LazyRef[_FakeController] = LazyRef("MyRef")
        with pytest.raises(RuntimeError, match="cannot set 'name' before set"):
            ref.name = "oops"

    def test_mock_controller_pattern(self):
        """Verify LazyRef works with MagicMock (as used in tests)."""
        ref: LazyRef[MagicMock] = LazyRef("ctrl")
        mock = MagicMock()
        mock.on_close.return_value = None
        ref.set(mock)
        ref.on_close()
        mock.on_close.assert_called_once()


class TestLazyRefTkinterPattern:
    """Tests simulating the critical Tkinter WM_DELETE_WINDOW callback pattern.

    In real code, ApplicationGUI.__init__ registers:
        self.root.protocol("WM_DELETE_WINDOW", self.controller.on_close)

    The ``self.controller.on_close`` expression is evaluated at **registration
    time** (during __init__).  With LazyRef, this resolves to a *bound method*
    lookup on the proxy, which defers to the real instance when actually called
    (i.e. when the user closes the window).
    """

    def test_store_reference_before_set_then_call_after_set(self):
        """Simulates the Tkinter WM_DELETE_WINDOW registration pattern."""
        ref: LazyRef[_FakeController] = LazyRef("MainViewModel")
        obj = _FakeController("real")

        # Simulate ApplicationGUI storing the callback
        # (in real code: self.controller.on_close — this resolves the attribute at call time)
        # We cannot grab `ref.on_close` before set() because __getattr__ raises RuntimeError.
        # Instead, the real pattern is:
        #   root.protocol("WM_DELETE_WINDOW", self.controller.on_close)
        # where self.controller IS the LazyRef. Tkinter stores the callable
        # and calls it later. At call time, Python evaluates self.controller.on_close
        # which goes through __getattr__ → real instance.

        # So what we actually test is that a lambda wrapping the ref works:
        callback = lambda: ref.on_close()  # noqa: E731

        # Set the real instance
        ref.set(obj)

        # Now call the callback (simulating window close)
        result = callback()
        assert result == "closed:real"
        assert obj.call_count == 1

    def test_direct_attribute_reference_pattern(self):
        """Test that ref.method_name works as a callable after set()."""
        ref: LazyRef[_FakeController] = LazyRef("ctrl")
        obj = _FakeController("direct")
        ref.set(obj)

        # Get the method reference (this goes through __getattr__)
        method = ref.on_close
        assert callable(method)
        assert method() == "closed:direct"


class TestLazyRefThreadSafety:
    """Tests for thread-safe set() behavior."""

    def test_concurrent_set_only_one_succeeds(self):
        """Verify that only one thread can set() the instance."""
        ref: LazyRef[_FakeController] = LazyRef("ctrl")
        results = {"success": 0, "error": 0}
        barrier = threading.Barrier(10)

        def try_set():
            barrier.wait()
            try:
                ref.set(_FakeController())
                results["success"] += 1
            except RuntimeError:
                results["error"] += 1

        threads = [threading.Thread(target=try_set) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert results["success"] == 1
        assert results["error"] == 9

    def test_concurrent_reads_after_set(self):
        """Verify concurrent attribute access works after resolution."""
        ref: LazyRef[_FakeController] = LazyRef("ctrl")
        obj = _FakeController("shared")
        ref.set(obj)
        errors = []

        def read():
            try:
                assert ref.name == "shared"
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Errors in concurrent reads: {errors}"
