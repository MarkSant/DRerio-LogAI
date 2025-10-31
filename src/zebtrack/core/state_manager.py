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

State Categories:
- Project State: current project path, metadata, configuration
- Detector State: active detector, zones, model settings
- Recording State: recording status, output paths, Arduino connection
- Processing State: current operation, progress, thread management
- UI State: view mode, selected videos, display settings

Quick Start Example:
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
class StateChange:
    """Record of a state change for debugging and history tracking."""

    timestamp: datetime
    category: StateCategory
    key: str
    old_value: Any
    new_value: Any
    source: str = "unknown"  # Which component triggered the change


@dataclass
class ProjectState:
    """Immutable snapshot of project-related state."""

    project_path: Path | None = None
    project_data: dict[str, Any] = field(default_factory=dict)
    metadata: Any | None = None  # DataFrame
    active_zone_video: str | None = None
    last_zone_source_video: str | None = None

    def copy(self) -> ProjectState:
        """Create a deep copy of project state."""
        return ProjectState(
            project_path=self.project_path,
            project_data=copy.deepcopy(self.project_data),
            metadata=self.metadata.copy() if self.metadata is not None else None,
            active_zone_video=self.active_zone_video,
            last_zone_source_video=self.last_zone_source_video,
        )


@dataclass
class DetectorState:
    """Immutable snapshot of detector-related state."""

    detector_initialized: bool = False
    active_weight_name: str = ""
    use_openvino: bool = False
    detector_plugin_name: str | None = None
    zones_configured: bool = False
    zone_data: Any | None = None  # ZoneData
    frame_width: int | None = None
    frame_height: int | None = None

    def copy(self) -> DetectorState:
        """Create a deep copy of detector state."""
        return DetectorState(
            detector_initialized=self.detector_initialized,
            active_weight_name=self.active_weight_name,
            use_openvino=self.use_openvino,
            detector_plugin_name=self.detector_plugin_name,
            zones_configured=self.zones_configured,
            zone_data=copy.deepcopy(self.zone_data),
            frame_width=self.frame_width,
            frame_height=self.frame_height,
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

    def copy(self) -> RecordingState:
        """Create a deep copy of recording state."""
        return RecordingState(
            is_recording=self.is_recording,
            output_path=self.output_path,
            recording_start_time=self.recording_start_time,
            arduino_connected=self.arduino_connected,
            arduino_port=self.arduino_port,
            timed_recording_active=self.timed_recording_active,
        )


@dataclass
class ProcessingState:
    """Immutable snapshot of processing-related state."""

    is_processing: bool = False
    processing_mode: str = "MULTI_TRACK"  # ProcessingMode enum
    current_video: str | None = None
    current_frame: int = 0
    total_frames: int = 0
    processing_start_time: datetime | None = None
    cancel_requested: bool = False

    def copy(self) -> ProcessingState:
        """Create a deep copy of processing state."""
        return ProcessingState(
            is_processing=self.is_processing,
            processing_mode=self.processing_mode,
            current_video=self.current_video,
            current_frame=self.current_frame,
            total_frames=self.total_frames,
            processing_start_time=self.processing_start_time,
            cancel_requested=self.cancel_requested,
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
        Called when observed state changes.

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
        Called when observed state changes.

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

    Example:
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

    Example Usage:
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

        log.info("state_manager.initialized", history_enabled=enable_history)

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

        Flow:
        1. Record change in history (if enabled)
        2. Notify category-specific observers
        3. Notify global observers
        4. Handle observer exceptions gracefully (log but don't propagate)

        Thread-safe: Already called within _lock context by update methods.

        Args:
            category: The category of state that changed
            key: The specific state key that changed
            old_value: The previous value
            new_value: The new value
            source: Identifier of the component that triggered the change
        """
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

        # Notify category-specific observers
        for observer in self._observers[category].copy():
            try:
                observer(category, key, old_value, new_value)
            except Exception:
                log.exception(
                    "state_manager.observer_failed",
                    category=category.name,
                    key=key,
                    observer=getattr(observer, "__name__", repr(observer)),
                )

        # Notify global observers
        for observer in self._global_observers.copy():
            try:
                observer(category, key, old_value, new_value)
            except Exception:
                log.exception(
                    "state_manager.global_observer_failed",
                    category=category.name,
                    key=key,
                    observer=getattr(observer, "__name__", repr(observer)),
                )

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
                ui=self.get_ui_state()
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
        """Returns frozen snapshot for debugging. DO NOT MODIFY."""

        def convert_paths_to_strings(d):
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

    # ==================== Project State Updates ====================

    def update_project_state(
        self,
        source: str = "unknown",
        **kwargs: Any,
    ) -> None:
        """
        Update project-related state fields.

        Args:
            source: Identifier of the component making the change
            **kwargs: State fields to update (e.g., project_path=Path(...))
        """
        with self._lock:
            for key, new_value in kwargs.items():
                if not hasattr(self._state.project, key):
                    log.warning(
                        "state_manager.unknown_project_key",
                        key=key,
                        source=source,
                    )
                    continue

                old_value = getattr(self._state.project, key)
                if old_value != new_value:
                    setattr(self._state.project, key, new_value)
                    self._notify_observers(
                        StateCategory.PROJECT,
                        key,
                        old_value,
                        new_value,
                        source,
                    )
                    log.debug(
                        "state_manager.project_updated",
                        key=key,
                        source=source,
                    )

    # ==================== Detector State Updates ====================

    def update_detector_state(
        self,
        source: str = "unknown",
        **kwargs: Any,
    ) -> None:
        """
        Update detector-related state fields.

        Args:
            source: Identifier of the component making the change
            **kwargs: State fields to update (e.g., detector_initialized=True)
        """
        with self._lock:
            for key, new_value in kwargs.items():
                if not hasattr(self._state.detector, key):
                    log.warning(
                        "state_manager.unknown_detector_key",
                        key=key,
                        source=source,
                    )
                    continue

                old_value = getattr(self._state.detector, key)
                if old_value != new_value:
                    setattr(self._state.detector, key, new_value)
                    self._notify_observers(
                        StateCategory.DETECTOR,
                        key,
                        old_value,
                        new_value,
                        source,
                    )
                    log.debug(
                        "state_manager.detector_updated",
                        key=key,
                        source=source,
                    )

    # ==================== Recording State Updates ====================

    def update_recording_state(
        self,
        source: str = "unknown",
        **kwargs: Any,
    ) -> None:
        """
        Update recording-related state fields.

        Args:
            source: Identifier of the component making the change
            **kwargs: State fields to update (e.g., is_recording=True)
        """
        with self._lock:
            for key, new_value in kwargs.items():
                if not hasattr(self._state.recording, key):
                    log.warning(
                        "state_manager.unknown_recording_key",
                        key=key,
                        source=source,
                    )
                    continue

                old_value = getattr(self._state.recording, key)
                if old_value != new_value:
                    setattr(self._state.recording, key, new_value)
                    self._notify_observers(
                        StateCategory.RECORDING,
                        key,
                        old_value,
                        new_value,
                        source,
                    )
                    log.debug(
                        "state_manager.recording_updated",
                        key=key,
                        source=source,
                    )

    # ==================== Processing State Updates ====================

    def update_processing_state(
        self,
        source: str = "unknown",
        **kwargs: Any,
    ) -> None:
        """
        Update processing-related state fields.

        Args:
            source: Identifier of the component making the change
            **kwargs: State fields to update (e.g., is_processing=True)
        """
        with self._lock:
            for key, new_value in kwargs.items():
                if not hasattr(self._state.processing, key):
                    log.warning(
                        "state_manager.unknown_processing_key",
                        key=key,
                        source=source,
                    )
                    continue

                old_value = getattr(self._state.processing, key)
                if old_value != new_value:
                    setattr(self._state.processing, key, new_value)
                    self._notify_observers(
                        StateCategory.PROCESSING,
                        key,
                        old_value,
                        new_value,
                        source,
                    )
                    log.debug(
                        "state_manager.processing_updated",
                        key=key,
                        source=source,
                    )

    # ==================== UI State Updates ====================

    def update_ui_state(
        self,
        source: str = "unknown",
        **kwargs: Any,
    ) -> None:
        """
        Update UI-related state fields.

        Args:
            source: Identifier of the component making the change
            **kwargs: State fields to update (e.g., canvas_view_mode="analysis")
        """
        with self._lock:
            for key, new_value in kwargs.items():
                if not hasattr(self._state.ui, key):
                    log.warning(
                        "state_manager.unknown_ui_key",
                        key=key,
                        source=source,
                    )
                    continue

                old_value = getattr(self._state.ui, key)
                if old_value != new_value:
                    setattr(self._state.ui, key, new_value)
                    self._notify_observers(
                        StateCategory.UI,
                        key,
                        old_value,
                        new_value,
                        source,
                    )
                    log.debug(
                        "state_manager.ui_updated",
                        key=key,
                        source=source,
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
                "project_data_keys": list(snapshot.project.project_data.keys()),
                "metadata_shape": snapshot.project.metadata.shape
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
                    "has_data": len(snapshot.project.project_data) > 0,
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
        """String representation for debugging."""
        history_info = (
            f", history={len(self._history)}/{self._max_history_size}"
            if self._enable_history
            else ""
        )
        observer_count = self.get_observer_count()
        return f"<StateManager observers={observer_count}{history_info}>"
