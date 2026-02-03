# State Management Architecture

**Category:** Explanation (Diátaxis)
**Status:** Canonical

## 1. The StateManager Agent

The `StateManager` is the centralized "Source of Truth" for all dynamic application data. It manages three main categories of state:

1.  **Project State:** Videos, groups, subjects, and experimental design.
2.  **Recording State:** Activity status, camera parameters, and hardware triggers.
3.  **UI State:** Tab selection, active video, and validation results.

## 2. Thread-Safe Observer Pattern

To ensure the UI stays synchronized with backend changes without causing deadlocks, the `StateManager` implements a **Safe Transition** notification system.

### 2.1. The Deadlock Problem
In early versions, observers were called while the `StateManager` held its internal `RLock`. If an observer tried to query the state again, the system would deadlock.

### 2.2. The Fix: Deferred Notification
State updates now follow a three-step process:
1.  **Atomic Update:** The state is updated inside the lock.
2.  **Notification Queueing:** A list of changes is compiled.
3.  **Outside Notification:** The lock is released **before** any observers are notified.

## 3. Best Practices for Observers

- **Main Thread Only:** Observers must wrap UI updates in `root.after(0, ...)` if there is any chance they are triggered from a background thread (e.g., during video analysis).
- **Idempotency:** Observers should check if the new value actually requires a UI change to avoid unnecessary flickering.
- **Error Isolation:** The `StateManager` catches and logs exceptions from individual observers to prevent one faulty component from breaking the entire notification chain.

---
**Reference:** For the implementation of state categories, see `src/zebtrack/core/state_manager.py`.
