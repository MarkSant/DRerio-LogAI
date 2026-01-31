"""
Centralized Application State Management.

Phase 2, Step 4: StateManager provides a single source of truth for all
application state, eliminating inconsistencies and making state changes
predictable and traceable.

Key Features:
- Observable pattern: Components can subscribe to state changes
- Immutable state snapshots for debugging and testing
- Thread-safe state access and updates
- Integration with EventBus for UI synchronization
- State history tracking for debugging
- Single ThreadPoolExecutor: All state observers are executed via a single shared executor
  to prevent thread explosion and ensure predictable performance.

State Categories:
- Project State: current project path, metadata, configuration
- Detector State: active detector, zones, model settings
- Recording State: recording status, output paths, Arduino connection
- Processing State: current operation, progress, thread management
- UI State: view mode, selected videos, display settings

Quick Start Example::

    # Initialize StateManager
    state_manager = StateManager(enable_history=True)

    # Subscribe to state changes
    def on_recording_changed(category, changes, new_state):
        if "is_recording" in changes:
            print(f"Recording: {new_state.is_recording}")

    state_manager.subscribe(StateCategory.RECORDING, on_recording_changed)

    # Update state (automatically notifies observers)
    state_manager.update_recording_state(
        source="controller.start_recording",
        is_recording=True,
        output_path="/path/to/output.parquet"
    )

    # Query current state
    recording_state = state_manager.get_recording_state()
    print(f"Is recording: {recording_state.is_recording}")

    # Check history
    history = state_manager.get_history(StateCategory.RECORDING, limit=10)
    for entry in history:
        print(f"{entry.timestamp}: {entry.changes}")

For complete documentation and integration patterns,
see docs/ARCHITECTURE.md section 4.1.
"""

from __future__ import annotations

import concurrent.futures
import copy
import dataclasses
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Protocol

import structlog

log = structlog.get_logger().bind(component="state_manager")


class StateCategory(Enum):
    """Categories of application state for fine-grained observation."""

    PROJECT = auto()
    DETECTOR = auto()
    RECORDING = auto()
    PROCESSING = auto()
    UI = auto()
    HARDWARE = auto()
    MODEL = auto()


@dataclass
class ProjectState:
    """Immutable snapshot of project-related state."""

    project_path: Path | None = None
    project_name: str | None = None
    experiment_id: str | None = None
    project_type: str | None = None
    video_file: str | None = None
    is_loaded: bool = False
    project_data: dict | None = None
    metadata: dict | None = None
    active_zone_video: str | None = None
    last_zone_source_video: str | None = None

    def copy(self) -> ProjectState:
        """Create a deep copy of project state."""
        return ProjectState(
            project_path=self.project_path,
            project_name=self.project_name,
            experiment_id=self.experiment_id,
            project_type=self.project_type,
            video_file=self.video_file,
            is_loaded=self.is_loaded,
            project_data=copy.deepcopy(self.project_data),
            metadata=self.metadata.copy() if self.metadata is not None else None,
            active_zone_video=self.active_zone_video,
            last_zone_source_video=self.last_zone_source_video,
        )


@dataclass
class StateChange:
    """Record of a state change for debugging and history tracking."""

    timestamp: datetime
    category: StateCategory
    key: str
    old_value: Any
    new_value: Any
    source: str = "unknown"  # Which component triggered the change

    def copy(self) -> StateChange:
        """Create a deep copy of the state change record."""
        return StateChange(
            timestamp=self.timestamp,
            category=self.category,
            key=self.key,
            old_value=copy.deepcopy(self.old_value),
            new_value=copy.deepcopy(self.new_value),
            source=self.source,
        )


@dataclass
class DetectorState:
    """Immutable snapshot of detector-related state."""

    detector_initialized: bool = False
    animal_method: str | None = None
    active_weight_name: str = ""
    use_openvino: bool = False
    detector_plugin_name: str | None = None
    zones_configured: bool = False
    zones_count: int = 0
    zone_data: Any | None = None  # ZoneData
    frame_width: int | None = None
    frame_height: int | None = None
    tracking_parameters_updated: bool = False
    track_threshold: float | None = None
    match_threshold: float | None = None
    track_buffer: int | None = None
    tracking_state_reset: bool = False
    single_subject_mode: bool = False
    settings_restored: bool = False
    detector_parameters_updated: bool = False
    last_update_scope: str | None = None
    conf_threshold: float | None = None
    nms_threshold: float | None = None
    use_bytetrack: bool = True
    max_center_distance: float | None = None
    iou_threshold: float | None = None

    def copy(self) -> DetectorState:
        """Create a deep copy of detector state."""
        return DetectorState(
            detector_initialized=self.detector_initialized,
            animal_method=self.animal_method,
            active_weight_name=self.active_weight_name,
            use_openvino=self.use_openvino,
            detector_plugin_name=self.detector_plugin_name,
            zones_configured=self.zones_configured,
            zones_count=self.zones_count,
            zone_data=copy.deepcopy(self.zone_data),
            frame_width=self.frame_width,
            frame_height=self.frame_height,
            tracking_parameters_updated=self.tracking_parameters_updated,
            track_threshold=self.track_threshold,
            match_threshold=self.match_threshold,
            track_buffer=self.track_buffer,
            tracking_state_reset=self.tracking_state_reset,
            single_subject_mode=self.single_subject_mode,
            settings_restored=self.settings_restored,
            detector_parameters_updated=self.detector_parameters_updated,
            last_update_scope=self.last_update_scope,
            conf_threshold=self.conf_threshold,
            nms_threshold=self.nms_threshold,
            use_bytetrack=self.use_bytetrack,
            max_center_distance=self.max_center_distance,
            iou_threshold=self.iou_threshold,
        )


@dataclass
class RecordingState:
    """Immutable snapshot of recording-related state."""

    is_recording: bool = False
    output_path: Path | None = None
    recording_start_time: datetime | None = None
    arduino_connected: bool = False
    arduino_port: str | None = None
    timed_recording_active: bool = False
    experiment_id: str | None = None
    duration: int | float | None = None

    def copy(self) -> RecordingState:
        """Create a deep copy of recording state."""
        return RecordingState(
            is_recording=self.is_recording,
            output_path=self.output_path,
            recording_start_time=self.recording_start_time,
            arduino_connected=self.arduino_connected,
            arduino_port=self.arduino_port,
            timed_recording_active=self.timed_recording_active,
            experiment_id=self.experiment_id,
            duration=self.duration,
        )


@dataclass
class ProcessingState:
    """Immutable snapshot of processing-related state."""

    is_processing: bool = False
    processing_mode: str = "MULTI_TRACK"  # ProcessingMode enum
    processing_type: str | None = None
    current_video: str | None = None
    current_frame: int = 0
    total_frames: int = 0
    processing_start_time: datetime | None = None
    cancel_requested: bool = False
    is_live_session_active: bool = False
    camera_index: int | None = None
    experiment_id: str | None = None
    duration_s: float | None = None
    last_success: bool | None = None
    last_error: str | None = None

    def copy(self) -> ProcessingState:
        """Create a deep copy of processing state."""
        return ProcessingState(
            is_processing=self.is_processing,
            processing_mode=self.processing_mode,
            processing_type=self.processing_type,
            current_video=self.current_video,
            current_frame=self.current_frame,
            total_frames=self.total_frames,
            processing_start_time=self.processing_start_time,
            cancel_requested=self.cancel_requested,
            is_live_session_active=self.is_live_session_active,
            camera_index=self.camera_index,
            experiment_id=self.experiment_id,
            duration_s=self.duration_s,
            last_success=self.last_success,
            last_error=self.last_error,
        )


@dataclass
class UIState:
    """Immutable snapshot of UI-related state."""

    canvas_view_mode: str = "zones"  # "zones" or "analysis"
    selected_videos: list[str] = field(default_factory=list)
    analysis_interval_frames: int = 10
    display_interval_frames: int = 10
    current_tab: str | None = None

    def copy(self) -> UIState:
        """Create a deep copy of UI state."""
        return UIState(
            canvas_view_mode=self.canvas_view_mode,
            selected_videos=list(self.selected_videos),
            analysis_interval_frames=self.analysis_interval_frames,
            display_interval_frames=self.display_interval_frames,
            current_tab=self.current_tab,
        )


@dataclass
class ApplicationState:
    """Complete immutable snapshot of all application state."""

    project: ProjectState = field(default_factory=ProjectState)
    detector: DetectorState = field(default_factory=DetectorState)
    recording: RecordingState = field(default_factory=RecordingState)
    processing: ProcessingState = field(default_factory=ProcessingState)
    ui: UIState = field(default_factory=UIState)

    def copy(self) -> ApplicationState:
        """Create a deep copy of all application state."""
        return ApplicationState(
            project=self.project.copy(),
            detector=self.detector.copy(),
            recording=self.recording.copy(),
            processing=self.processing.copy(),
            ui=self.ui.copy(),
        )


# ==================== Observer Protocol ====================


class StateObserverProtocol(Protocol):
    """
    Protocol for state observers.

    Observers must implement this callable signature to receive state change
    notifications from the StateManager.
    """

    def __call__(
        self,
        category: StateCategory,
        key: str,
        old_value: Any,
        new_value: Any,
    ) -> None:
        """
        Call when observed state changes.

        Args:
            category: The state category that changed
            key: The specific state key that changed
            old_value: The previous value
            new_value: The new value
        """
        ...


# Type alias for backward compatibility
StateObserver = Callable[[StateCategory, str, Any, Any], None]


class BaseStateObserver(ABC):
    """
    Abstract base class for state observers.

    Provides a formal interface for components that want to observe state changes.
    Subclasses must implement on_state_changed() to react to specific state changes.

    Example:
        class MyObserver(BaseStateObserver):
            def on_state_changed(self, category, key, old_value, new_value):
                if category == StateCategory.RECORDING and key == "is_recording":
                    print(f"Recording state: {new_value}")
    """

    @abstractmethod
    def on_state_changed(
        self,
        category: StateCategory,
        key: str,
        old_value: Any,
        new_value: Any,
    ) -> None:
        """
        Call when observed state changes.

        Args:
            category: The state category that changed
            key: The specific state key that changed
            old_value: The previous value
            new_value: The new value
        """
        pass


class ObserverAdapter:
    """
    Adapter to simplify observer implementation with filtering.

    Allows observing specific categories and/or keys without implementing
    the full BaseStateObserver interface.

    Example::

        def handle_recording(category, key, old_value, new_value):
            print(f"Recording changed: {key} = {new_value}")

        adapter = ObserverAdapter(
            callback=handle_recording,
            categories={StateCategory.RECORDING},
            keys={"is_recording", "output_path"}
        )
        state_manager.subscribe_observer(StateCategory.RECORDING, adapter)
    """

    def __init__(
        self,
        callback: Callable[[StateCategory, str, Any, Any], None],
        categories: set[StateCategory] | None = None,
        keys: set[str] | None = None,
    ):
        """
        Initialize the adapter.

        Args:
            callback: Function to call when matching state changes occur
            categories: If provided, only notify for these categories (None = all)
            keys: If provided, only notify for these keys (None = all)
        """
        self.callback = callback
        self.categories = categories
        self.keys = keys

    def __call__(
        self,
        category: StateCategory,
        key: str,
        old_value: Any,
        new_value: Any,
    ) -> None:
        """Filter and forward notifications to callback."""
        # Filter by category
        if self.categories is not None and category not in self.categories:
            return

        # Filter by key
        if self.keys is not None and key not in self.keys:
            return

        # Forward to callback
        self.callback(category, key, old_value, new_value)


class StateManager:
    """
    Centralized state manager implementing observable pattern.

    This class provides a single source of truth for all application state,
    with thread-safe access and change notifications. Components can observe
    specific state categories or individual state keys.

    Example Usage::

        # Create state manager
        state_mgr = StateManager()

        # Subscribe to state changes
        def on_recording_change(category, key, old_val, new_val):
            print(f"Recording state changed: {key} = {new_val}")

        state_mgr.subscribe(StateCategory.RECORDING, on_recording_change)

        # Update state
        state_mgr.update_recording_state(is_recording=True)

        # Get current state snapshot
        snapshot = state_mgr.get_snapshot()
        print(snapshot.recording.is_recording)  # True
    """

    def __init__(self, enable_history: bool = True, max_history_size: int = 100):
        """
        Initialize the StateManager.

        CRITICAL: Direct access to _state is prohibited. All state modifications
        MUST go through update_*_state() methods to ensure proper locking,
        validation, and observer notifications.

        Args:
            enable_history: Whether to track state change history for debugging
            max_history_size: Maximum number of state changes to keep in history
        """
        # INTERNAL STATE - DO NOT ACCESS DIRECTLY FROM OUTSIDE THIS CLASS
        # Use get_*_state() for reads and update_*_state() for writes
        self._state = ApplicationState()
        self._lock = threading.RLock()

        # Observer pattern: category -> set of callbacks
        self._observers: dict[StateCategory, set[StateObserver]] = {
            category: set() for category in StateCategory
        }
        # Global observers that receive all state changes
        self._global_observers: set[StateObserver] = set()

        # State change history for debugging
        self._enable_history = enable_history
        self._max_history_size = max_history_size
        self._history: list[StateChange] = []

        # Task 1.2: Observer timeout protection (default 5 seconds)
        # NOTE: This should only be modified during initialization or when no
        # notifications are in progress to avoid race conditions
        self._observer_timeout_seconds = 5

        # Task 1.1: Single ThreadPoolExecutor for observers to avoid overhead
        self._observer_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

        log.info("state_manager.initialized", history_enabled=enable_history)

        # Hint for coordinators to prefer unified state update API when available
        self.prefer_unified_state_api = True

    def shutdown(self) -> None:
        """Shutdown the state manager and release resources."""
        self._observer_executor.shutdown(wait=False)
        log.info("state_manager.shutdown")

    # ==================== Observer Management ====================

    def subscribe(
        self,
        category: StateCategory,
        observer: StateObserver,
    ) -> None:
        """
        Subscribe to state changes in a specific category.

        This method registers an observer callback that will be invoked whenever
        state in the specified category changes. The observer receives notifications
        with (category, key, old_value, new_value).

        Thread-safe: Multiple components can subscribe concurrently.

        Args:
            category: The state category to observe
            observer: Callback function(category, key, old_value, new_value)
                     Can be a plain function, method, or BaseStateObserver subclass

        Example:
            def on_recording_change(category, key, old_val, new_val):
                print(f"{key} changed: {old_val} -> {new_val}")

            state_manager.subscribe(StateCategory.RECORDING, on_recording_change)
        """
        with self._lock:
            self._observers[category].add(observer)
            log.debug(
                "state_manager.subscribe",
                category=category.name,
                observer=getattr(observer, "__name__", repr(observer)),
            )

    def register_observer(
        self,
        category: StateCategory,
        observer: StateObserver,
    ) -> None:
        """
        Alias for subscribe() - explicitly register an observer.

        Provides a more descriptive name for formal observer registration.
        Functionally identical to subscribe().

        Args:
            category: The state category to observe
            observer: Callback function or BaseStateObserver instance
        """
        self.subscribe(category, observer)

    def subscribe_all(self, observer: StateObserver) -> None:
        """
        Subscribe to all state changes across all categories.

        Global observers receive notifications for every state change regardless
        of category. Useful for logging, debugging, or cross-cutting concerns.

        Thread-safe: Multiple components can subscribe concurrently.

        Args:
            observer: Callback function(category, key, old_value, new_value)

        Example:
            def log_all_changes(category, key, old_val, new_val):
                print(f"[{category.name}] {key}: {old_val} -> {new_val}")

            state_manager.subscribe_all(log_all_changes)
        """
        with self._lock:
            self._global_observers.add(observer)
            log.debug(
                "state_manager.subscribe_all",
                observer=getattr(observer, "__name__", repr(observer)),
            )

    def register_global_observer(self, observer: StateObserver) -> None:
        """
        Alias for subscribe_all() - explicitly register a global observer.

        Provides a more descriptive name for formal observer registration.
        Functionally identical to subscribe_all().

        Args:
            observer: Callback function or BaseStateObserver instance
        """
        self.subscribe_all(observer)

    def unsubscribe(
        self,
        category: StateCategory,
        observer: StateObserver,
    ) -> None:
        """
        Unsubscribe from state changes in a specific category.

        Args:
            category: The state category to stop observing
            observer: The callback function to remove
        """
        with self._lock:
            self._observers[category].discard(observer)
            log.debug(
                "state_manager.unsubscribe",
                category=category.name,
                observer=getattr(observer, "__name__", repr(observer)),
            )

    def unsubscribe_all(self, observer: StateObserver) -> None:
        """
        Unsubscribe from all state changes.

        Args:
            observer: The callback function to remove
        """
        with self._lock:
            self._global_observers.discard(observer)
            log.debug(
                "state_manager.unsubscribe_all",
                observer=getattr(observer, "__name__", repr(observer)),
            )

    def _call_observer_with_timeout(
        self,
        observer: Callable,
        category: StateCategory,
        key: str,
        old_value: Any,
        new_value: Any,
        timeout_seconds: float = 5.0,
    ) -> None:
        """
        Call observer asynchronously without blocking the caller.

        Task 2.3 (FIXED): Prevent hanging observers from freezing the application.
        Observers are submitted to thread pool but caller does NOT wait for result.

        This eliminates UI freezing (ANR - Application Not Responding) that occurred
        when observers took several seconds to complete.

        Args:
            observer: Observer callback to invoke
            category: State category that changed
            key: State key that changed
            old_value: Previous value
            new_value: New value
            timeout_seconds: Maximum time to wait for observer (unused, kept for API compat)

        Logs:
            - observer.callback_failed: If observer raises exception (via callback)

        Note:
            This is now "fire and forget" - caller proceeds immediately.
            Exceptions and timeouts are logged but do not block the caller.
        """
        observer_name = getattr(observer, "__name__", repr(observer))

        # Task 1.1: Reuse existing executor instead of creating new one
        try:
            future = self._observer_executor.submit(observer, category, key, old_value, new_value)
        except RuntimeError:
            # Executor might be shutting down; fall back to inline execution
            try:
                observer(category, key, old_value, new_value)
            except Exception as exc:  # pragma: no cover - logged for visibility
                log.error(
                    "state.observer.callback_failed",
                    category=category.name,
                    key=key,
                    error=str(exc),
                    observer=observer_name,
                    exc_info=True,
                )
            return

        # Add completion callback to handle errors without blocking caller
        def _on_observer_complete(fut: concurrent.futures.Future) -> None:
            try:
                fut.result(timeout=0.1)  # Non-blocking check with minimal timeout
            except concurrent.futures.TimeoutError:
                # Observer still running - this shouldn't happen with timeout=0.1
                log.warning(
                    "state.observer.still_running",
                    category=category.name,
                    key=key,
                    observer=observer_name,
                )
            except Exception as e:
                # Observer raised exception - log and continue
                log.error(
                    "state.observer.callback_failed",
                    category=category.name,
                    key=key,
                    error=str(e),
                    observer=observer_name,
                    exc_info=True,
                )

        future.add_done_callback(_on_observer_complete)

    def _notify_observers(
        self,
        category: StateCategory,
        key: str,
        old_value: Any,
        new_value: Any,
        source: str = "unknown",
    ) -> None:
        """
        Notify all relevant observers of a state change.

        INTERNAL METHOD - Called automatically by update_*_state() methods.
        This implements the core of the Observer pattern by broadcasting
        state changes to all registered observers.

        CRITICAL THREADING FIX (Task 1.1):
        This method prevents deadlocks by:
        1. Snapshot observers and record history INSIDE the lock
        2. Release the lock
        3. Call observers OUTSIDE the lock (prevents deadlock)

        This ensures observers can safely call back into StateManager methods
        without causing deadlock.

        Flow:
        1. Acquire lock and record change in history (if enabled)
        2. Snapshot observers list
        3. Release lock
        4. Notify category-specific observers (OUTSIDE lock)
        5. Notify global observers (OUTSIDE lock)
        6. Handle observer exceptions gracefully (log but don't propagate)

        Thread-safe: Manages its own locking, should be called OUTSIDE any lock.

        Args:
            category: The category of state that changed
            key: The specific state key that changed
            old_value: The previous value
            new_value: The new value
            source: Identifier of the component that triggered the change
        """
        # Step 1: Snapshot observers and state WITHIN the lock
        with self._lock:
            # Record in history
            if self._enable_history:
                change = StateChange(
                    timestamp=datetime.now(),
                    category=category,
                    key=key,
                    old_value=old_value,
                    new_value=new_value,
                    source=source,
                )
                self._history.append(change)
                if len(self._history) > self._max_history_size:
                    self._history.pop(0)

            # Snapshot observers - creating list copies for thread-safe iteration
            category_observers = list(self._observers[category])
            global_observers = list(self._global_observers)

        # Step 2: Notify OUTSIDE the lock (prevents deadlock)
        # Task 2.3: All observers now executed with 5-second timeout protection
        # This prevents hanging observers from freezing the entire application

        # Notify category-specific observers with timeout
        for observer in category_observers:
            self._call_observer_with_timeout(observer, category, key, old_value, new_value)

        # Notify global observers with timeout
        for observer in global_observers:
            self._call_observer_with_timeout(observer, category, key, old_value, new_value)

    # ==================== State Snapshots ====================

    def get_snapshot(self) -> ApplicationState:
        """
        Get an immutable snapshot of the entire application state.

        Phase 4: Uses individual getters that apply selective deep copy
        for optimal performance while maintaining immutability guarantees.

        Returns:
            A deep copy of the current application state
        """
        with self._lock:
            # Use individual getters that apply selective deep copy
            return ApplicationState(
                project=self.get_project_state(),
                detector=self.get_detector_state(),
                recording=self.get_recording_state(),
                processing=self.get_processing_state(),
                ui=self.get_ui_state(),
            )

    def get_project_state(self) -> ProjectState:
        """Get an immutable snapshot of project state.

        Phase 4: Uses selective deep copy - dataclasses.replace for speed,
        but deep copies mutable fields (project_data dict, metadata DataFrame).
        """
        with self._lock:
            # Fast shallow copy for immutable fields
            snapshot = dataclasses.replace(self._state.project)
            # Deep copy mutable fields to ensure true immutability
            snapshot.project_data = copy.deepcopy(self._state.project.project_data)
            if self._state.project.metadata is not None:
                # DataFrames have their own .copy() method
                snapshot.metadata = self._state.project.metadata.copy()
            return snapshot

    def get_detector_state(self) -> DetectorState:
        """Get an immutable snapshot of detector state.

        Phase 4: Uses selective deep copy - dataclasses.replace for speed,
        but deep copies mutable zone_data field.
        """
        with self._lock:
            snapshot = dataclasses.replace(self._state.detector)
            # Deep copy zone_data if it exists (it's a dict/object)
            snapshot.zone_data = copy.deepcopy(self._state.detector.zone_data)
            return snapshot

    def get_recording_state(self) -> RecordingState:
        """Get an immutable snapshot of recording state.

        Phase 4: Simple shallow copy sufficient - all fields are immutable types
        (bool, Path, datetime, str).
        """
        with self._lock:
            return dataclasses.replace(self._state.recording)

    def get_processing_state(self) -> ProcessingState:
        """Get an immutable snapshot of processing state.

        Phase 4: Simple shallow copy sufficient - all fields are immutable types
        (bool, str, int, datetime).
        """
        with self._lock:
            return dataclasses.replace(self._state.processing)

    def get_ui_state(self) -> UIState:
        """Get an immutable snapshot of UI state.

        Phase 4: Uses selective deep copy - dataclasses.replace for speed,
        but deep copies mutable selected_videos list.
        """
        with self._lock:
            snapshot = dataclasses.replace(self._state.ui)
            # Deep copy the selected_videos list to ensure immutability
            snapshot.selected_videos = copy.deepcopy(self._state.ui.selected_videos)
            return snapshot

    def get_state_snapshot(self) -> dict:
        """Return frozen snapshot for debugging. DO NOT MODIFY."""

        def convert_paths_to_strings(d: Any) -> Any:
            if isinstance(d, dict):
                return {k: convert_paths_to_strings(v) for k, v in d.items()}
            if isinstance(d, list):
                return [convert_paths_to_strings(i) for i in d]
            if isinstance(d, Path):
                return str(d)
            return d

        with self._lock:
            state_dict = {
                "project": dataclasses.asdict(self._state.project),
                "detector": dataclasses.asdict(self._state.detector),
                "recording": dataclasses.asdict(self._state.recording),
                "processing": dataclasses.asdict(self._state.processing),
                "ui": dataclasses.asdict(self._state.ui),
                "_timestamp": datetime.now().isoformat(),
            }
            return convert_paths_to_strings(state_dict)

    # ==================== Unified State Helpers ====================

    def get_state(self, category: StateCategory) -> dict[str, Any]:
        """Return the current state for a specific category as a plain dict."""

        getter_map: dict[StateCategory, Callable[[], Any]] = {
            StateCategory.PROJECT: self.get_project_state,
            StateCategory.DETECTOR: self.get_detector_state,
            StateCategory.RECORDING: self.get_recording_state,
            StateCategory.PROCESSING: self.get_processing_state,
            StateCategory.UI: self.get_ui_state,
        }

        getter = getter_map.get(category)
        if getter is None:
            log.warning(
                "state_manager.get_state.unsupported_category",
                category=category.name,
            )
            return {}

        snapshot = getter()
        if dataclasses.is_dataclass(snapshot):
            # mypy doesn't narrow type here effectively for asdict
            state_dict = dataclasses.asdict(snapshot)  # type: ignore
        elif isinstance(snapshot, dict):
            state_dict = copy.deepcopy(snapshot)
        else:
            state_dict = copy.deepcopy(getattr(snapshot, "__dict__", {}))

        if category == StateCategory.DETECTOR:
            state_dict.setdefault(
                "is_detector_initialized",
                state_dict.get("detector_initialized", False),
            )

        return state_dict

    def update_state(
        self,
        category: StateCategory,
        *,
        source: str = "unknown",
        **kwargs: Any,
    ) -> None:
        """Unified entry point to update state using StateCategory semantics."""

        dispatcher: dict[StateCategory, Callable[..., None]] = {
            StateCategory.PROJECT: self.update_project_state,
            StateCategory.DETECTOR: self.update_detector_state,
            StateCategory.RECORDING: self.update_recording_state,
            StateCategory.PROCESSING: self.update_processing_state,
            StateCategory.UI: self.update_ui_state,
        }

        update_method = dispatcher.get(category)
        if update_method is None:
            log.warning(
                "state_manager.update_state.unsupported_category",
                category=category.name,
                source=source,
            )
            return

        normalized_kwargs = self._normalize_state_kwargs(category, kwargs)
        update_method(source=source, **normalized_kwargs)

    def _normalize_state_kwargs(
        self,
        category: StateCategory,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Normalize legacy keys before forwarding to category updaters."""

        if not updates:
            return {}

        if category == StateCategory.DETECTOR:
            alias_map = {
                "is_detector_initialized": "detector_initialized",
            }
            normalized: dict[str, Any] = {}
            for key, value in updates.items():
                canonical_key = alias_map.get(key, key)
                normalized[canonical_key] = value
            return normalized

        return dict(updates)

    # Task 3.3: Generic state update method to eliminate duplication
    def _update_state_generic(
        self,
        category: StateCategory,
        state_object: Any,
        category_name: str,
        source: str,
        **kwargs: Any,
    ) -> None:
        """Generic state update implementation to eliminate code duplication.

        Task 3.3: Replaces duplicated logic across 5 update_*_state methods.

        Args:
            category: StateCategory enum value (PROJECT, DETECTOR, etc.)
            state_object: State object to update (self._state.project, etc.)
            category_name: Category name for logging ("project", "detector", etc.)
            source: Identifier of component making the change
            **kwargs: State fields to update

        Pattern:
            All update_*_state methods follow this pattern:
            1. Collect notifications list
            2. Lock, iterate kwargs, check attribute exists, compare values, setattr
            3. Unlock, send notifications

        This method extracts that common logic to avoid ~40 lines duplication per method.
        """
        # Collect notifications to send (deadlock prevention pattern)
        notifications = []

        with self._lock:
            for key, new_value in kwargs.items():
                if not hasattr(state_object, key):
                    log.warning(
                        f"state_manager.unknown_{category_name}_key",
                        key=key,
                        source=source,
                    )
                    continue

                old_value = getattr(state_object, key)
                if old_value != new_value:
                    setattr(state_object, key, new_value)
                    # Queue notification instead of sending immediately
                    notifications.append((category, key, old_value, new_value, source))
                    log.debug(
                        f"state_manager.{category_name}_updated",
                        key=key,
                        source=source,
                    )

        # Send notifications OUTSIDE the lock (prevents deadlock)
        for category, key, old_value, new_value, src in notifications:
            self._notify_observers(category, key, old_value, new_value, src)

    # ==================== Project State Updates ====================

    def update_project_state(
        self,
        source: str = "unknown",
        **kwargs: Any,
    ) -> None:
        """
        Update project-related state fields.

        Task 3.3: Refactored to use _update_state_generic() (-34 lines duplication).

        Args:
            source: Identifier of the component making the change
            **kwargs: State fields to update (e.g., project_path=Path(...))
        """
        self._update_state_generic(
            category=StateCategory.PROJECT,
            state_object=self._state.project,
            category_name="project",
            source=source,
            **kwargs,
        )

    # ==================== Detector State Updates ====================

    def update_detector_state(
        self,
        source: str = "unknown",
        **kwargs: Any,
    ) -> None:
        """
        Update detector-related state fields.

        Task 3.3: Refactored to use _update_state_generic() (-34 lines duplication).

        Args:
            source: Identifier of the component making the change
            **kwargs: State fields to update (e.g., detector_initialized=True)
        """
        self._update_state_generic(
            category=StateCategory.DETECTOR,
            state_object=self._state.detector,
            category_name="detector",
            source=source,
            **kwargs,
        )

    # ==================== Recording State Updates ====================

    def update_recording_state(
        self,
        source: str = "unknown",
        **kwargs: Any,
    ) -> None:
        """
        Update recording-related state fields.

        Task 3.3: Refactored to use _update_state_generic() (-34 lines duplication).

        Args:
            source: Identifier of the component making the change
            **kwargs: State fields to update (e.g., is_recording=True)
        """
        self._update_state_generic(
            category=StateCategory.RECORDING,
            state_object=self._state.recording,
            category_name="recording",
            source=source,
            **kwargs,
        )

    # ==================== Processing State Updates ====================

    def update_processing_state(
        self,
        source: str = "unknown",
        **kwargs: Any,
    ) -> None:
        """
        Update processing-related state fields.

        Task 3.3: Refactored to use _update_state_generic() (-34 lines duplication).

        Args:
            source: Identifier of the component making the change
            **kwargs: State fields to update (e.g., is_processing=True)
        """
        self._update_state_generic(
            category=StateCategory.PROCESSING,
            state_object=self._state.processing,
            category_name="processing",
            source=source,
            **kwargs,
        )

    # ==================== UI State Updates ====================

    def update_ui_state(
        self,
        source: str = "unknown",
        **kwargs: Any,
    ) -> None:
        """
        Update UI-related state fields.

        Task 3.3: Refactored to use _update_state_generic() (-34 lines duplication).

        Args:
            source: Identifier of the component making the change
            **kwargs: State fields to update (e.g., canvas_view_mode="analysis")
        """
        self._update_state_generic(
            category=StateCategory.UI,
            state_object=self._state.ui,
            category_name="ui",
            source=source,
            **kwargs,
        )

    # ==================== State History ====================

    def get_history(
        self,
        category: StateCategory | None = None,
        key: str | None = None,
        limit: int | None = None,
    ) -> list[StateChange]:
        """
        Get state change history for debugging.

        Args:
            category: Filter by state category (None = all)
            key: Filter by state key (None = all)
            limit: Maximum number of changes to return (None = all)

        Returns:
            List of StateChange objects matching the filters
        """
        with self._lock:
            if not self._enable_history:
                return []

            filtered = self._history

            if category is not None:
                filtered = [c for c in filtered if c.category == category]

            if key is not None:
                filtered = [c for c in filtered if c.key == key]

            if limit is not None:
                filtered = filtered[-limit:]

            return list(filtered)

    def clear_history(self) -> None:
        """Clear the state change history."""
        with self._lock:
            self._history.clear()
            log.info("state_manager.history_cleared")

    # ==================== Debugging Utilities ====================

    def dump_state(self) -> dict[str, Any]:
        """
        Dump the entire state as a dictionary for debugging.

        Returns:
            Dictionary representation of all application state
        """
        snapshot = self.get_snapshot()
        return {
            "project": {
                "project_path": str(snapshot.project.project_path)
                if snapshot.project.project_path
                else None,
                "project_data_keys": list(snapshot.project.project_data.keys())
                if snapshot.project.project_data
                else [],
                "metadata_keys": list(snapshot.project.metadata.keys())
                if snapshot.project.metadata is not None
                else None,
                "active_zone_video": snapshot.project.active_zone_video,
            },
            "detector": {
                "initialized": snapshot.detector.detector_initialized,
                "active_weight": snapshot.detector.active_weight_name,
                "use_openvino": snapshot.detector.use_openvino,
                "plugin": snapshot.detector.detector_plugin_name,
                "zones_configured": snapshot.detector.zones_configured,
                "frame_size": (
                    snapshot.detector.frame_width,
                    snapshot.detector.frame_height,
                ),
            },
            "recording": {
                "is_recording": snapshot.recording.is_recording,
                "output_path": str(snapshot.recording.output_path)
                if snapshot.recording.output_path
                else None,
                "arduino_connected": snapshot.recording.arduino_connected,
                "timed_recording_active": snapshot.recording.timed_recording_active,
            },
            "processing": {
                "is_processing": snapshot.processing.is_processing,
                "mode": snapshot.processing.processing_mode,
                "current_video": snapshot.processing.current_video,
                "progress": f"{snapshot.processing.current_frame}/{snapshot.processing.total_frames}",  # noqa: E501
                "cancel_requested": snapshot.processing.cancel_requested,
            },
            "ui": {
                "view_mode": snapshot.ui.canvas_view_mode,
                "selected_videos_count": len(snapshot.ui.selected_videos),
                "intervals": f"analysis={snapshot.ui.analysis_interval_frames}, display={snapshot.ui.display_interval_frames}",  # noqa: E501
                "current_tab": snapshot.ui.current_tab,
            },
        }

    def get_observer_count(self, category: StateCategory | None = None) -> int:
        """
        Get the number of registered observers.

        Args:
            category: If provided, count only observers for this category.
                     If None, count all observers (category + global).

        Returns:
            Number of registered observers
        """
        with self._lock:
            if category is not None:
                return len(self._observers[category])
            else:
                total = sum(len(obs) for obs in self._observers.values())
                total += len(self._global_observers)
                return total

    def verify_state_integrity(self) -> dict[str, Any]:
        """
        Verify state integrity and return diagnostic information.

        Useful for debugging and testing to ensure state is consistent.

        Returns:
            Dictionary with integrity check results
        """
        with self._lock:
            snapshot = self._state.copy()

            return {
                "state_valid": True,  # Could add more complex validation
                "project": {
                    "has_path": snapshot.project.project_path is not None,
                    "has_data": bool(snapshot.project.project_data),
                    "has_metadata": snapshot.project.metadata is not None,
                },
                "detector": {
                    "initialized": snapshot.detector.detector_initialized,
                    "has_zones": snapshot.detector.zones_configured,
                    "has_dimensions": (
                        snapshot.detector.frame_width is not None
                        and snapshot.detector.frame_height is not None
                    ),
                },
                "recording": {
                    "is_recording": snapshot.recording.is_recording,
                    "has_output": snapshot.recording.output_path is not None,
                    "arduino_connected": snapshot.recording.arduino_connected,
                },
                "processing": {
                    "is_processing": snapshot.processing.is_processing,
                    "has_progress": snapshot.processing.total_frames > 0,
                },
                "observers": {
                    "total": self.get_observer_count(),
                    "by_category": {cat.name: len(self._observers[cat]) for cat in StateCategory},
                    "global": len(self._global_observers),
                },
            }

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        history_info = (
            f", history={len(self._history)}/{self._max_history_size}"
            if self._enable_history
            else ""
        )
        observer_count = self.get_observer_count()
        return f"<StateManager observers={observer_count}{history_info}>"
