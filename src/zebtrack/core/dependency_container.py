from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zebtrack.coordinators.dialog_coordinator import DialogCoordinator
    from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator

import structlog

from zebtrack.analysis.analysis_service import AnalysisService

# Phase 3 → Phase 4: Super Coordinators
# ProcessingCoordinator decomposed into 5 sub-coordinators (Phase 4)
# SessionCoordinator decomposed into 3 sub-coordinators (Phase 4.7)
# HardwareCoordinator decomposed into 2 sub-coordinators (Phase 4.9)
from zebtrack.coordinators.detector_setup_coordinator import DetectorSetupCoordinator
from zebtrack.coordinators.live_calibration_coordinator import LiveCalibrationCoordinator
from zebtrack.coordinators.live_camera_session_coordinator import LiveCameraSessionCoordinator
from zebtrack.coordinators.model_diagnostics_coordinator import ModelDiagnosticsCoordinator
from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
from zebtrack.coordinators.recording_session_coordinator import RecordingSessionCoordinator
from zebtrack.coordinators.ui_state_coordinator import UIStateController
from zebtrack.coordinators.video_processing_coordinator import VideoProcessingCoordinator
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.core.project.project_workflow_service import ProjectWorkflowService
from zebtrack.core.recording.live_camera_service import LiveCameraService
from zebtrack.core.recording.recording_service import RecordingService
from zebtrack.core.services.detector_service import DetectorService
from zebtrack.core.services.model_service import ModelService
from zebtrack.core.services.weight_manager import WeightManager
from zebtrack.core.state_manager import StateManager
from zebtrack.core.ui_scheduler import UIScheduler
from zebtrack.core.video.video_processing_service import VideoProcessingService
from zebtrack.settings import Settings
from zebtrack.ui.event_bus_v2 import EventBusV2
from zebtrack.ui.project_workflow_adapter import ProjectWorkflowAdapter

log = structlog.get_logger()


class LazyRef[T]:
    """Thread-safe transparent proxy that defers attribute access until a real instance is set.

    Solves the circular dependency problem where ``ApplicationGUI.__init__`` stores
    ``self.controller`` and registers ``self.controller.on_close`` as a Tkinter
    ``WM_DELETE_WINDOW`` callback **before** ``MainViewModel.__init__`` has run.

    With ``LazyRef``, the GUI receives the proxy at construction time.  Attribute
    look-ups (e.g. ``controller.on_close``) are forwarded to the real instance
    only when actually *invoked* (i.e. when the user closes the window, long after
    ``LazyRef.set()`` has been called).

    Usage::

        ref: LazyRef[MainViewModel] = LazyRef("MainViewModel")
        # ... pass ref to ApplicationGUI / UIStateController ...
        controller = MainViewModel(dependencies, bootstrap_result)
        ref.set(controller)  # all subsequent attribute access goes to controller

    Raises:
        RuntimeError: If an attribute is accessed before ``set()`` is called **and**
            the access cannot be deferred (e.g. calling a method immediately).
    """

    def __init__(self, name: str = "LazyRef") -> None:
        # Use object.__setattr__ to bypass our __setattr__ override
        object.__setattr__(self, "_lock", threading.Lock())
        object.__setattr__(self, "_instance", None)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_resolved", False)

    # -- Public API ----------------------------------------------------------

    def set(self, instance: T) -> None:
        """Bind the real instance.  Must be called exactly once."""
        with self._lock:
            if self._resolved:
                raise RuntimeError(
                    f"LazyRef({self._name}): instance already set. "
                    "set() must be called exactly once."
                )
            object.__setattr__(self, "_instance", instance)
            object.__setattr__(self, "_resolved", True)
            log.debug("lazy_ref.resolved", name=self._name, type=type(instance).__name__)

    def get(self) -> T:
        """Return the real instance, or raise if not yet resolved."""
        if not self._resolved:
            raise RuntimeError(
                f"LazyRef({self._name}): instance not yet set. "
                "Call set() before accessing the wrapped object."
            )
        return self._instance  # type: ignore[return-value]

    @property
    def is_resolved(self) -> bool:
        """Whether ``set()`` has been called."""
        return self._resolved  # type: ignore[return-value]

    # -- Transparent proxy ---------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to the wrapped instance.

        This makes ``LazyRef`` act as a *transparent proxy*: code that holds a
        reference to the proxy can call ``proxy.on_close`` and it will resolve
        to ``real_instance.on_close`` at call time.

        Raises ``RuntimeError`` if called before ``set()``.
        """
        # _lock, _instance, _name, _resolved are handled by object.__getattribute__
        # via __init__ (set with object.__setattr__).  If we get here, the attribute
        # is NOT one of ours → delegate to the wrapped instance.
        instance = object.__getattribute__(self, "_instance")
        resolved = object.__getattribute__(self, "_resolved")
        if not resolved:
            ref_name = object.__getattribute__(self, "_name")
            raise RuntimeError(
                f"LazyRef({ref_name}): cannot access '{name}' before set() is called."
            )
        return getattr(instance, name)

    def __setattr__(self, name: str, value: Any) -> None:
        """Forward attribute writes to the wrapped instance (post-resolution)."""
        # Guard: our own internal attrs are set via object.__setattr__ in __init__/set
        if name in ("_lock", "_instance", "_name", "_resolved"):
            object.__setattr__(self, name, value)
            return
        instance = object.__getattribute__(self, "_instance")
        resolved = object.__getattribute__(self, "_resolved")
        if not resolved:
            ref_name = object.__getattribute__(self, "_name")
            raise RuntimeError(f"LazyRef({ref_name}): cannot set '{name}' before set() is called.")
        setattr(instance, name, value)

    def __repr__(self) -> str:
        name = object.__getattribute__(self, "_name")
        resolved = object.__getattribute__(self, "_resolved")
        if resolved:
            instance = object.__getattribute__(self, "_instance")
            return f"<LazyRef({name}) → {type(instance).__name__}>"
        return f"<LazyRef({name}) [unresolved]>"


@dataclass
class MainViewModelDependencies:
    """Encapsulates all dependencies required by MainViewModel.

    This reduces the number of arguments in MainViewModel.__init__ and
    makes dependency injection more structured.

    Phase 3 Update:
        - Added 4 super coordinators (ProjectLifecycleCoordinator, HardwareCoordinator,
          ProcessingCoordinator, SessionCoordinator)
    Phase 4.9 Update:
        - HardwareCoordinator decomposed into DetectorSetupCoordinator +
          ModelDiagnosticsCoordinator
        - Removed LEGACY detector_coordinator field
    """

    # Core infrastructure
    root: Any  # tk.Tk
    settings_obj: Settings
    event_bus: EventBusV2 | None
    state_manager: StateManager
    ui_coordinator: UIScheduler  # Renamed from UICoordinator to avoid collision

    # Domain managers
    project_manager: ProjectManager
    project_workflow_service: ProjectWorkflowService
    weight_manager: WeightManager
    model_service: ModelService

    # Domain services
    detector_service: DetectorService
    video_processing_service: VideoProcessingService
    analysis_service: AnalysisService | None = None
    recording_service: RecordingService | None = None
    live_camera_service: LiveCameraService | None = None
    ui_state_controller: UIStateController | None = None
    dialog_coordinator: DialogCoordinator | None = None

    # Phase 3 → Phase 4: Super Coordinators
    # processing_coordinator now is VideoProcessingCoordinator (Phase 4 decomposition)
    # session_coordinator decomposed into 3 sub-coordinators (Phase 4.7)
    # hardware_coordinator decomposed into 2 sub-coordinators (Phase 4.9)
    project_lifecycle_coordinator: ProjectLifecycleCoordinator | None = None
    detector_setup_coordinator: DetectorSetupCoordinator | None = None
    model_diagnostics_coordinator: ModelDiagnosticsCoordinator | None = None
    processing_coordinator: VideoProcessingCoordinator | None = None
    recording_session_coordinator: RecordingSessionCoordinator | None = None
    live_camera_session_coordinator: LiveCameraSessionCoordinator | None = None
    live_calibration_coordinator: LiveCalibrationCoordinator | None = None
    project_workflow_adapter: ProjectWorkflowAdapter | None = None
    live_batch_coordinator: LiveBatchCoordinator | None = None  # v2.3.0

    # Phase 6: LazyRef for breaking circular dependency (replaces __new__ two-phase init)
    controller_ref: LazyRef | None = None

    # Runtime State
    cancel_event: Any = None

    # Testing
    test_sync_event: Any = None
