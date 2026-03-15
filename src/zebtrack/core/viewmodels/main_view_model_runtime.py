"""Runtime event/state handlers for MainViewModel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.core.state_manager import StateCategory
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import Event, UIEvents

if TYPE_CHECKING:
    from zebtrack.core.main_view_model import MainViewModel

log = structlog.get_logger()


def _payload_to_dict(
    payload: payloads.EventPayload | dict[str, Any] | None,
) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    if is_dataclass(payload) and not isinstance(payload, type):
        return asdict(payload)
    return {}


def _payload_get(
    payload: payloads.EventPayload | dict[str, Any] | None,
    key: str,
    default=None,
):
    if payload is None:
        return default
    if isinstance(payload, dict):
        return payload.get(key, default)
    if is_dataclass(payload) and not isinstance(payload, type):
        return getattr(payload, key, default)
    return default


class MainViewModelRuntime:
    """Extracted event/state handlers to keep MainViewModel lean."""

    _EVENTS_TO_HANDLE = (
        UIEvents.RECORDING_START,
        UIEvents.RECORDING_STOP,
        UIEvents.RECORDING_TOGGLE,
        UIEvents.PROJECT_CREATE,
        UIEvents.PROJECT_OPEN,
        UIEvents.PROJECT_CLOSE,
        UIEvents.MODEL_SET_OPENVINO,
        UIEvents.MODEL_SET_WEIGHT,
        UIEvents.MODEL_RUN_DIAGNOSTIC,
        UIEvents.UI_REQUEST_WEIGHT_FILE,
        UIEvents.UI_OPEN_MANAGE_WEIGHTS_DIALOG,
        UIEvents.VIDEO_ANALYZE_SINGLE,
        UIEvents.VIDEO_CANCEL_ANALYSIS,
        UIEvents.MODEL_ADD_WEIGHT,
        UIEvents.MODEL_DELETE_WEIGHT,
        UIEvents.MODEL_LOAD_NEW_WEIGHT,
        UIEvents.MODEL_MANAGE_WEIGHTS,
        UIEvents.ZONE_SAVE_MANUAL_ARENA,
        UIEvents.PROJECT_DELETE_ASSET,
        UIEvents.CALIBRATION_COPY_TO_PROJECT,
        UIEvents.CALIBRATION_SAVE_TO_PROJECT,
        UIEvents.PROJECT_GENERATE_SUMMARIES,
        UIEvents.PROJECT_VIDEO_SELECTED,
        UIEvents.PROJECT_SELECTION_CHANGED,
    )

    def __init__(self, view_model: MainViewModel) -> None:
        self._vm = view_model

    def register_event_handlers(self) -> None:
        if not self._vm.ui_event_bus:
            return

        for event_name in self._EVENTS_TO_HANDLE:
            dispatcher = self._create_event_handler(event_name)
            self._vm.ui_event_bus.subscribe(event_name, dispatcher)

        self._vm.ui_event_bus.subscribe(
            UIEvents.PROJECT_MANAGER_REPLACED,
            self.handle_project_manager_replaced,
        )

    def _create_event_handler(
        self, event_name: UIEvents
    ) -> Callable[[payloads.EventPayload], None]:
        def handler(data: payloads.EventPayload) -> None:
            self.handle_event(event_name, data)

        return handler

    def handle_event(self, event_name: UIEvents, data: payloads.EventPayload) -> None:
        payload_dict = _payload_to_dict(data)

        match event_name:
            case UIEvents.RECORDING_START | UIEvents.RECORDING_STOP | UIEvents.RECORDING_TOGGLE:
                self._handle_recording_event(event_name)
            case UIEvents.PROJECT_CREATE | UIEvents.PROJECT_OPEN | UIEvents.PROJECT_CLOSE:
                self._handle_project_event(event_name, data, payload_dict)
            case (
                UIEvents.MODEL_SET_OPENVINO
                | UIEvents.MODEL_SET_WEIGHT
                | UIEvents.MODEL_RUN_DIAGNOSTIC
                | UIEvents.MODEL_ADD_WEIGHT
                | UIEvents.MODEL_DELETE_WEIGHT
                | UIEvents.MODEL_LOAD_NEW_WEIGHT
                | UIEvents.MODEL_MANAGE_WEIGHTS
                | UIEvents.UI_REQUEST_WEIGHT_FILE
                | UIEvents.UI_OPEN_MANAGE_WEIGHTS_DIALOG
            ):
                self._handle_model_event(event_name, data, payload_dict)
            case UIEvents.VIDEO_ANALYZE_SINGLE | UIEvents.VIDEO_CANCEL_ANALYSIS:
                self._handle_video_event(event_name, data)
            case UIEvents.ZONE_SAVE_MANUAL_ARENA:
                self._handle_zone_event(data)
            case (
                UIEvents.PROJECT_DELETE_ASSET
                | UIEvents.CALIBRATION_COPY_TO_PROJECT
                | UIEvents.CALIBRATION_SAVE_TO_PROJECT
                | UIEvents.PROJECT_GENERATE_SUMMARIES
                | UIEvents.PROJECT_VIDEO_SELECTED
                | UIEvents.PROJECT_SELECTION_CHANGED
            ):
                self._handle_project_misc_event(event_name, data, payload_dict)
            case _:
                log.debug(
                    "main_view_model.event_handler.unhandled",
                    event_name=event_name.name,
                )

    def _handle_recording_event(self, event_name: UIEvents) -> None:
        vm = self._vm
        if event_name is UIEvents.RECORDING_START:
            vm.hardware_vm.start_recording()
        elif event_name is UIEvents.RECORDING_STOP:
            vm.hardware_vm.stop_recording()
        elif event_name is UIEvents.RECORDING_TOGGLE:
            vm.hardware_vm.toggle_recording()

    def _handle_project_event(
        self,
        event_name: UIEvents,
        data: payloads.EventPayload,
        payload_dict: dict[str, Any],
    ) -> None:
        vm = self._vm
        if event_name is UIEvents.PROJECT_CREATE:
            vm.project_vm.create_project_workflow(**payload_dict)
        elif event_name is UIEvents.PROJECT_OPEN:
            project_path = _payload_get(data, "project_path")
            if project_path:
                vm.project_vm.open_project_workflow(project_path)
        elif event_name is UIEvents.PROJECT_CLOSE:
            vm.project_vm.close_project()

    def _handle_model_event(
        self,
        event_name: UIEvents,
        data: payloads.EventPayload,
        payload_dict: dict[str, Any],
    ) -> None:
        vm = self._vm
        if event_name is UIEvents.MODEL_SET_OPENVINO:
            vm.hardware_vm.set_openvino_usage(**payload_dict)
        elif event_name is UIEvents.MODEL_SET_WEIGHT:
            vm.hardware_vm.set_active_weight(**payload_dict)
        elif event_name is UIEvents.MODEL_RUN_DIAGNOSTIC:
            config = _payload_get(data, "config", {}) or {}
            vm.hardware_vm.run_model_diagnostic(config)
        elif event_name is UIEvents.UI_REQUEST_WEIGHT_FILE:
            vm.hardware_vm.handle_request_weight_file()
        elif event_name is UIEvents.UI_OPEN_MANAGE_WEIGHTS_DIALOG:
            vm.hardware_vm.handle_open_manage_weights(vm.root)
        elif event_name is UIEvents.MODEL_ADD_WEIGHT:
            vm.hardware_vm.add_new_weight(**payload_dict)
        elif event_name is UIEvents.MODEL_DELETE_WEIGHT:
            vm.hardware_vm.delete_weight(**payload_dict)
        elif event_name is UIEvents.MODEL_LOAD_NEW_WEIGHT:
            vm.hardware_vm.load_new_weight(**payload_dict)
        elif event_name is UIEvents.MODEL_MANAGE_WEIGHTS:
            vm.hardware_vm.manage_weights()

    def _handle_video_event(self, event_name: UIEvents, data: payloads.EventPayload) -> None:
        vm = self._vm
        if event_name is UIEvents.VIDEO_ANALYZE_SINGLE:
            video_path = _payload_get(data, "video_path")
            config = _payload_get(data, "config", {}) or {}
            if video_path:
                vm.analysis_vm.start_single_video_workflow(
                    video_path, config, detector_vm=vm.hardware_vm
                )
        elif event_name is UIEvents.VIDEO_CANCEL_ANALYSIS:
            vm.analysis_vm.cancel_current_analysis()

    def _handle_zone_event(self, data: payloads.EventPayload) -> None:
        polygon_points = _payload_get(data, "polygon_points")
        if polygon_points is not None:
            self._vm.analysis_vm.save_manual_arena(polygon_points)

    def _handle_project_misc_event(
        self,
        event_name: UIEvents,
        data: payloads.EventPayload,
        payload_dict: dict[str, Any],
    ) -> None:
        vm = self._vm
        if event_name is UIEvents.PROJECT_DELETE_ASSET:
            if payload_dict:
                vm.project_vm.handle_delete_project_asset(**payload_dict)
        elif event_name is UIEvents.CALIBRATION_COPY_TO_PROJECT:
            vm.project_vm.handle_calibration_copy_to_project()
        elif event_name is UIEvents.CALIBRATION_SAVE_TO_PROJECT:
            vm.project_vm.handle_calibration_save_to_project()
        elif event_name is UIEvents.PROJECT_GENERATE_SUMMARIES:
            video_paths = _payload_get(data, "video_paths")
            if video_paths is not None:
                vm.analysis_vm.generate_parquet_summaries(list(video_paths))
        elif event_name is UIEvents.PROJECT_VIDEO_SELECTED:
            video_path = _payload_get(data, "video_path")
            if video_path:
                vm.project_vm.on_video_selected(video_path)
        elif event_name is UIEvents.PROJECT_SELECTION_CHANGED:
            video_path = _payload_get(data, "video_path")
            if not video_path:
                selection = _payload_get(data, "selection", [])
                if selection:
                    video_path = selection[0]
            if video_path:
                vm.project_vm.on_video_selected(video_path)

    def on_project_state_changed(
        self, category: StateCategory, key: str, old: Any, new: Any
    ) -> None:
        if not self._vm.ui_event_bus:
            return
        if key in ("active_zone_video", "project_data"):
            zone_data = self._vm.project_manager.get_zone_data()
            self._vm.ui_event_bus.publish(Event(UIEvents.UI_REDRAW_ZONES, {"zone_data": zone_data}))
            self._vm.ui_event_bus.publish(
                Event(UIEvents.UI_UPDATE_ZONE_LIST, {"zone_data": zone_data})
            )

    def on_detector_state_changed(
        self, category: StateCategory, key: str, old: Any, new: Any
    ) -> None:
        if not self._vm.ui_event_bus:
            return
        if key == "active_weight_name":
            self._vm.ui_event_bus.publish(
                Event(UIEvents.UI_SET_ACTIVE_WEIGHT, {"weight_name": new})
            )
        elif key == "use_openvino":
            self._vm.ui_event_bus.publish(
                Event(UIEvents.UI_UPDATE_OPENVINO_CHECKBOX, {"is_checked": new})
            )
            self._vm.ui_state_controller.update_openvino_status()

    def on_processing_state_changed(
        self, category: StateCategory, key: str, old: Any, new: Any
    ) -> None:
        log.debug(
            "controller.processing_state_changed",
            key=key,
            old=old,
            new=new,
            has_ui_event_bus=bool(self._vm.ui_event_bus),
        )
        if key == "is_processing":
            if new:
                if self._vm.ui_event_bus:
                    event_type = UIEvents.UI_NAVIGATE_TO_ANALYSIS_VIEW
                    log.info(
                        "controller.navigating_to_analysis_view",
                        event_name=event_type.name,
                        event_bus_id=id(self._vm.ui_event_bus),
                    )
                    self._vm.ui_event_bus.publish(Event(event_type))
                    log.info("controller.event_published")
                else:
                    log.warning("controller.ui_event_bus_not_available")
        elif key == "cancel_requested" and new:
            self._vm.ui_state_controller._show_cancel_feedback()

    def handle_project_manager_replaced(self, data: payloads.EventPayload) -> None:
        new_manager = _payload_get(data, "new_manager")
        if not new_manager:
            return

        if hasattr(self._vm, "project_workflow_adapter") and self._vm.project_workflow_adapter:
            self._vm.project_workflow_adapter.project_manager = new_manager

        services_to_update = [
            ("project_workflow_service", self._vm.project_workflow_service),
            ("detector_service", self._vm.detector_service),
            ("video_processing_service", self._vm.video_processing_service),
            ("recording_service", self._vm.recording_service),
            ("processing_coordinator", self._vm.processing_coordinator),
        ]

        orchestrators_to_update: list[tuple[str, Any]] = [
            # Phase 0.3: VideoProcessingOrchestrator removed
            # Phase 3A/B/C/D: Removed superseded orchestrators
        ]

        for name, service in services_to_update + orchestrators_to_update:
            if service and hasattr(service, "_on_project_manager_replaced"):
                try:
                    service._on_project_manager_replaced(data)
                except Exception as exc:  # pragma: no cover - orchestration boundary
                    log.error(
                        "main_view_model.project_manager_replaced.service_update_failed",
                        service=name,
                        error=str(exc),
                    )
            elif service and hasattr(service, "project_manager"):
                try:
                    service.project_manager = new_manager
                except AttributeError as exc:
                    log.error(
                        "main_view_model.project_manager_replaced.direct_update_failed",
                        service=name,
                        error=str(exc),
                    )

    def join_threads(self) -> None:
        vm = self._vm
        log.info("controller.shutdown.start")

        vm.program_exit_event.set()
        vm.analysis_vm.cancel_current_analysis()

        if vm.processing_coordinator and vm.processing_coordinator.processing_thread:
            if vm.processing_coordinator.processing_thread.is_alive():
                log.info("controller.shutdown.joining_processing_coordinator_thread")
                vm.processing_coordinator.processing_thread.join(timeout=5.0)

        if vm.processing_thread and vm.processing_thread.is_alive():
            log.info("controller.shutdown.joining_legacy_processing_thread")
            vm.processing_thread.join(timeout=5.0)

        capture_thread = getattr(vm, "capture_thread", None)
        if capture_thread and capture_thread.is_alive():
            log.info("controller.shutdown.joining_capture_thread")
            capture_thread.join(timeout=5.0)

        camera_release_success = True
        camera = getattr(vm.hardware_vm, "camera", None)
        if not camera and hasattr(vm, "camera"):
            camera = vm.camera

        if camera:
            try:
                camera_release_success = bool(camera.release())
            except Exception as exc:
                camera_release_success = False
                log.error("controller.camera.release_failed", error=str(exc))

        if not camera_release_success:
            log.critical(
                "controller.camera.zombie_detected",
                message="Camera thread did not shut down cleanly",
            )
            if vm.ui_event_bus:
                vm.ui_event_bus.publish(
                    Event(
                        UIEvents.ERROR_OCCURRED,
                        {
                            "title": "Erro Crítico",
                            "message": (
                                "A thread da câmera não foi finalizada corretamente. "
                                "O aplicativo será encerrado."
                            ),
                        },
                    )
                )

        vm.hardware_vm._shutdown_arduino_manager()
        log.info("controller.shutdown.complete")
