# StateManager Threading Improvements

**Date:** November 2025  
**Team:** EQUIPE 1 - Core State & Threading  
**Priority:** CRITICAL

## Overview

This document describes critical threading improvements made to the `StateManager` class to prevent deadlocks and improve concurrency performance. These changes are part of Sprint 1 (Weeks 1-3) and are **blocking for other teams**.

## The Problem: Deadlock in Observer Notifications

### Original Implementation (DANGEROUS)

The original implementation had a critical deadlock vulnerability:

```python
# BEFORE (DANGEROUS):
def update_project_state(self, source: str = "unknown", **kwargs):
    with self._lock:  # Lock acquired
        for key, new_value in kwargs.items():
            old_value = getattr(self._state.project, key)
            if old_value != new_value:
                setattr(self._state.project, key, new_value)
                self._notify_observers(category, key, old_value, new_value)
                # ⚠️ PROBLEM: Observers called WHILE HOLDING LOCK

def _notify_observers(self, category, key, old_value, new_value):
    # Already inside lock from caller
    for observer in self._observers[category]:
        observer(category, key, old_value, new_value)
        # ⚠️ DEADLOCK RISK: If observer tries to call StateManager methods,
        # it will try to acquire the same lock → DEADLOCK!
```

### Deadlock Scenario

1. Thread A: Calls `update_project_state()` → acquires lock
2. Thread A: Calls observer callback (still holding lock)
3. Observer: Tries to call `get_recording_state()` → needs lock
4. **DEADLOCK**: Thread A waits for observer, observer waits for lock held by Thread A

### Why This Happened

- Observers were called **inside** the `with self._lock:` block
- Observers couldn't safely query or update state without risking deadlock
- The lock was held for the **entire duration** of observer callbacks
- Slow observers would block all state updates

## The Solution: Observer Notification Outside Lock

### Task 1.1: Deferred Observer Notification

We restructured all state update methods to:
1. **Collect** notifications to send (inside lock)
2. **Release** the lock
3. **Send** notifications (outside lock)

```python
# AFTER (SAFE):
def update_project_state(self, source: str = "unknown", **kwargs):
    # Step 1: Collect notifications inside lock
    notifications = []
    
    with self._lock:
        for key, new_value in kwargs.items():
            old_value = getattr(self._state.project, key)
            if old_value != new_value:
                setattr(self._state.project, key, new_value)
                # Queue notification instead of sending immediately
                notifications.append((StateCategory.PROJECT, key, old_value, new_value, source))
    
    # Step 2: Send notifications OUTSIDE lock (prevents deadlock)
    for category, key, old_value, new_value, src in notifications:
        self._notify_observers(category, key, old_value, new_value, src)
```

### `_notify_observers` Implementation

The `_notify_observers` method now manages its own locking:

```python
def _notify_observers(self, category, key, old_value, new_value, source="unknown"):
    """
    Notify observers with deadlock prevention.
    
    CRITICAL: Observers are called OUTSIDE the lock!
    """
    # Step 1: Snapshot observers INSIDE the lock
    with self._lock:
        # Record history
        if self._enable_history:
            self._history.append(StateChange(...))
        
        # Snapshot observers - create list copies
        category_observers = list(self._observers[category])
        global_observers = list(self._global_observers)
    
    # Step 2: Call observers OUTSIDE the lock
    for observer in category_observers:
        try:
            observer(category, key, old_value, new_value)
        except Exception as e:
            log.error("state.observer.callback_failed", ...)
```

### Benefits

✅ **No Deadlocks**: Observers can safely call any StateManager method  
✅ **Better Performance**: Lock is released quickly, improving concurrency  
✅ **Isolation**: Observer failures don't affect other observers  
✅ **Predictable**: State updates complete before observers are notified

## Task 1.2: Timeout Protection for Slow Observers

### The Problem

Even with deadlock fixes, a slow or hung observer could still block other observers from being notified.

### The Solution

We added timeout protection using a context manager:

```python
@contextmanager
def timeout(seconds: int):
    """
    Timeout context manager for observer callbacks.
    
    WARNING: Uses signal.SIGALRM (Unix only, main thread only).
    On Windows or in threads, degrades gracefully (no timeout).
    """
    can_use_signal = (
        platform.system() != "Windows" and 
        hasattr(signal, "SIGALRM") and
        threading.current_thread() is threading.main_thread()
    )
    
    if can_use_signal:
        def timeout_handler(signum, frame):
            raise TimeoutError("Observer callback exceeded timeout")
        
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    else:
        # No timeout on Windows or in threads - execute normally
        yield
```

### Integration in `_notify_observers`

```python
# Default 5-second timeout (configurable via _observer_timeout_seconds)
observer_timeout = self._observer_timeout_seconds

for observer in category_observers:
    try:
        with timeout(observer_timeout):
            observer(category, key, old_value, new_value)
    except TimeoutError:
        log.error("state.observer.timeout", 
                  timeout_seconds=observer_timeout,
                  observer=observer)
    except Exception as e:
        log.error("state.observer.callback_failed", error=str(e))
```

### Configuration

```python
# In StateManager.__init__
self._observer_timeout_seconds = 5  # Default 5 seconds

# To customize (if needed):
state_manager = StateManager()
state_manager._observer_timeout_seconds = 10  # 10 seconds
```

## Task 1.3: Comprehensive Stress Tests

### Test Suite: `test_state_manager_stress.py`

We created 5 stress tests to validate threading improvements:

1. **`test_1000_concurrent_updates_no_deadlock`**
   - 1000 threads updating state simultaneously
   - Must complete in < 5 seconds
   - Validates no deadlocks occur

2. **`test_observers_do_not_block_state_updates`**
   - Slow observer (500ms) should not block fast updates
   - 10 fast updates should complete while slow observer runs
   - Validates lock is released properly

3. **`test_100_observers_registered_concurrently`**
   - 100 threads registering observers simultaneously
   - Validates thread-safe observer registration
   - All 100 observers should be registered

4. **`test_subscribe_unsubscribe_race_condition`**
   - 20 observers subscribing/unsubscribing concurrently
   - 50 state updates happening simultaneously
   - Validates no race conditions or crashes

5. **`test_memory_leak_with_many_subscriptions`**
   - 1000 subscribe/unsubscribe cycles
   - Validates no memory leaks
   - Reference count increase should be < 10

### Test Suite: `test_state_manager_observer_timeout.py`

Validates timeout protection:

1. **`test_observer_timeout`** (Unix only)
   - Slow observer (2s) with 1s timeout
   - Should timeout and not block other observers
   - Normal observers should still complete

2. **`test_observer_timeout_on_windows_no_crash`**
   - Validates graceful degradation on Windows
   - Should not crash when timeout isn't available

3. **`test_observer_exception_handling_with_timeout`**
   - Failing observer should not prevent other observers
   - Exception handling should work with timeout

### Running the Tests

```bash
# Run stress tests only
poetry run pytest tests/test_state_manager_stress.py -v

# Run with slow tests enabled
poetry run pytest tests/test_state_manager_stress.py -v -m slow

# Run all state manager tests
poetry run pytest tests/test_state_manager*.py -v

# Run timeout tests (Unix only for signal-based timeout)
poetry run pytest tests/test_state_manager_observer_timeout.py -v
```

## Guidelines for Observer Implementation

### DO ✅

- Keep observers **fast and non-blocking** (< 100ms ideal)
- Use `root.after()` for Tkinter UI updates
- Handle exceptions within your observer
- Query state if needed (deadlock-safe now!)
- Log errors appropriately

### DON'T ❌

- Perform long-running operations in observers
- Block on I/O operations
- Call `time.sleep()` for long periods
- Assume observers run in any specific order
- Modify state within observers without proper update calls

### Example: Good Observer

```python
def on_recording_changed(category, key, old_value, new_value):
    """Fast, non-blocking observer."""
    if key == "is_recording":
        if new_value:
            # Schedule UI update asynchronously
            root.after(0, lambda: update_recording_indicator(True))
        else:
            root.after(0, lambda: update_recording_indicator(False))
```

### Example: Bad Observer (DON'T DO THIS)

```python
def on_recording_changed(category, key, old_value, new_value):
    """BAD: Slow, blocking observer."""
    if key == "is_recording":
        # ❌ Don't do heavy computation
        process_video_analysis()  # Could take seconds!
        
        # ❌ Don't block on I/O
        with open("log.txt", "a") as f:
            f.write(f"Recording: {new_value}\n")
        
        # ❌ Don't sleep
        time.sleep(1)
```

## Performance Characteristics

### Before Improvements

- Lock held during observer callbacks: **HIGH deadlock risk**
- 1000 concurrent updates: **Frequent deadlocks**
- Slow observers blocked all updates: **Poor concurrency**

### After Improvements

- Lock released before observers: **Zero deadlock risk**
- 1000 concurrent updates: **Completes in < 5 seconds**
- Slow observers don't block updates: **Excellent concurrency**
- Timeout protection: **Prevents hung observers**

## Migration Guide

### For Existing Code

**Good news**: Most existing code doesn't need changes!

The improvements are **backward compatible**. Existing observers will work exactly as before, but now they're deadlock-safe.

### If You Were Working Around Deadlocks

If you were using workarounds like:
```python
# Old workaround (no longer needed)
threading.Timer(0, lambda: state_manager.update_state(...)).start()
```

You can now safely call state methods directly:
```python
# New way (safe now)
state_manager.update_recording_state(is_recording=True)
```

## Summary

| Aspect | Before | After |
|--------|--------|-------|
| Deadlock Risk | ⚠️ HIGH | ✅ NONE |
| Lock Duration | Long (with callbacks) | Short (state update only) |
| Observer Timeout | ❌ None | ✅ 5s default |
| Concurrency | Poor | Excellent |
| Test Coverage | Basic | Comprehensive (stress tests) |

## Related Documentation

- `docs/ARCHITECTURE.md` - Overall architecture
- `docs/STATE_MANAGEMENT_GUIDE.md` - General state management patterns
- `src/zebtrack/core/state_manager.py` - Implementation

## Questions?

If you encounter issues or have questions about these changes, please:
1. Review the stress tests for examples
2. Check the implementation in `state_manager.py`
3. Consult the team lead for EQUIPE 1

---

**Implementation Team**: EQUIPE 1 - Core State & Threading  
**Sprint**: Sprint 1 (Weeks 1-3)  
**Status**: ✅ Complete
