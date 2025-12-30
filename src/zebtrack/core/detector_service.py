"""
Detector Service for ZebTrack-AI.

Phase 6: Service layer for detector and zone management.

Handles detector initialization, zone configuration, tracking parameter
updates, and plugin context management operations.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Literal

import structlog

from zebtrack.core.detector import Detector, ZoneData
from zebtrack.settings import save_settings
from zebtrack.utils import IntegrityError

if TYPE_CHECKING:
    from zebtrack.core.model_service import ModelService
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.weight_manager import WeightManager
    from zebtrack.plugins.base import DetectorPlugin
    from zebtrack.settings import Settings

log = structlog.get_logger()

# Default thresholds - should match config.yaml values
DEFAULT_TRACK_THRESHOLD = 0.25
DEFAULT_MATCH_THRESHOLD = 0.80  # Higher for stable tracking with sparse frames


class DetectorService:
    """
    Service for managing detector initialization, zones, and tracking configuration.

    Phase 6: Extracted from MainViewModel to separate detector management
    concerns from controller orchestration logic.

    Responsibilities:
    - Detector initialization and plugin management
    - Zone configuration and scaling
    - Tracking parameter updates (ByteTrack, single-subject mode)
    - Plugin context management (tracking/diagnostic modes)
    - Detector state persistence
    """

    def __init__(
        self,
        state_manager: StateManager,
        project_manager: ProjectManager,
        weight_manager: WeightManager,
        model_service: ModelService,
        settings_obj: Settings,
    ):
        """
        Initialize DetectorService.

        Args:
            state_manager: StateManager for centralized state tracking
            project_manager: ProjectManager for zone data and config persistence
            weight_manager: WeightManager for model path resolution
            model_service: ModelService for weight details and OpenVINO paths
            settings_obj: Settings instance (injected dependency)
        """
        self.state_manager = state_manager
        self.project_manager = project_manager
        self.weight_manager = weight_manager
        self.model_service = model_service
        self.settings = settings_obj

        # Detector instance (managed by this service)
        self.detector: Detector | None = None

        log.info("detector_service.initialized")

    def initialize_detector(
        self,
        animal_method: str | None = None,
        use_openvino: bool = False,
        active_weight_name: str | None = None,
        detector_plugins: dict | None = None,
    ) -> tuple[bool, str | None]:
        """
        Initialize the detector instance based on the animal method selection.

        Phase 6: Extracted from controller.setup_detector()

        Args:
            animal_method: Detection method ('det' or 'seg'). If None, uses global settings
            use_openvino: Whether to use OpenVINO plugin
            active_weight_name: Current active weight name for state tracking
            detector_plugins: Dict mapping plugin names to plugin classes

        Returns:
            tuple: (success: bool, error_message: str | None)
        """
        # Use temporary override if provided, otherwise use global settings
        animal_method = animal_method or self.settings.model_selection.animal_method
        log.info(
            "detector_service.initialize.start",
            animal_method=animal_method,
            use_openvino=use_openvino,
        )

        # Get weight path based on animal method
        model_path = self.weight_manager.get_weight_path_by_method(animal_method, "animal")
        log.info(
            "detector_service.model_path_selected",
            animal_method=animal_method,
            task="animal",
            model_path=model_path,
        )

        if not model_path:
            error_msg = f"Nenhum modelo {animal_method} está disponível para detecção de animais."
            log.error("detector_service.no_model_path", error=error_msg)
            return False, error_msg

        # Find weight and get correct model path
        weight_name, weight_details = self.model_service.find_weight_by_path(model_path)
        if not weight_name:
            error_msg = f"Não foi possível encontrar o peso correspondente ao caminho: {model_path}"
            log.error("detector_service.weight_not_found", error=error_msg)
            return False, error_msg

        try:
            # Resolve plugin and model path
            if use_openvino:
                plugin_name = "OpenVINO"
                final_model_path, weight_details = self.model_service.get_model_path_for_inference(
                    weight_name, use_openvino=True
                )
                if not final_model_path:
                    raise ValueError(
                        "Caminho do modelo OpenVINO não encontrado ou inválido. "
                        "Por favor, converta o modelo primeiro."
                    )
                model_path = final_model_path
            else:
                plugin_name = "YOLO (Ultralytics)"
                if not os.path.exists(model_path):
                    raise ValueError("Caminho do modelo YOLO .pt não encontrado ou inválido.")

            # Get plugin class
            if detector_plugins is None:
                from zebtrack.plugins import DETECTOR_PLUGINS

                detector_plugins = DETECTOR_PLUGINS

            plugin_class = detector_plugins.get(plugin_name)
            if not plugin_class:
                raise ValueError(f"Detector plugin '{plugin_name}' not found.")

            log.info(
                "detector_service.load.start",
                plugin=plugin_name,
                path=model_path,
                method=animal_method,
            )

            # Instantiate plugin with settings
            if use_openvino:
                expected_hash = weight_details.get("openvino_hash")
                plugin_instance = plugin_class(
                    model_path=model_path, expected_hash=expected_hash, settings_obj=self.settings
                )
            else:
                plugin_instance = plugin_class(model_path=model_path, settings_obj=self.settings)

            # MELHORIA #2: Validar classes esperadas pelo sistema
            self._validate_model_classes(plugin_instance, model_path)

            # Create detector instance
            self.detector = Detector(
                plugin=plugin_instance,
                base_width=self.settings.camera.desired_width,
                base_height=self.settings.camera.desired_height,
                settings_obj=self.settings,
            )

            # Update detector state in StateManager
            self.state_manager.update_detector_state(
                source="detector_service.initialize",
                detector_initialized=True,
                active_weight_name=active_weight_name,
                use_openvino=use_openvino,
                detector_plugin_name=plugin_instance.get_name()
                if hasattr(plugin_instance, "get_name")
                else plugin_class.__name__,
            )

            # Configure single-subject tracker preference
            tracker_pref = self._resolve_single_subject_tracker_preference(None)
            if tracker_pref is None:
                tracker_pref = self.settings.tracking.use_single_subject_tracker
            else:
                self.settings.tracking.use_single_subject_tracker = tracker_pref
            self.set_single_subject_mode(tracker_pref)
            log.info(
                "detector_service.single_subject_tracker.configured",
                enabled=tracker_pref,
            )

            # Set context for tracking
            if hasattr(plugin_instance, "set_context"):
                plugin_instance.set_context("tracking")
                log.info("detector_service.context.set", context="tracking")

            # Save detector state to project
            detector_config = self._build_detector_config(plugin_instance, use_openvino)
            save_result = self.project_manager.save_detector_state(detector_config)
            if save_result:
                log.info("detector_service.state.saved", config=detector_config)
            else:
                log.warning("detector_service.state.save_failed")

            log.info("detector_service.initialize.success", method=animal_method)
            return True, None

        except (ValueError, FileNotFoundError, IntegrityError) as e:
            log.error("detector_service.initialize.failed", error=str(e), exc_info=True)
            error_msg = f"Falha ao inicializar o detector: {e}"
            return False, error_msg

    def configure_zones(
        self,
        zones_data: ZoneData | None = None,
        *legacy_dimensions: int,
        video_width: int | None = None,
        video_height: int | None = None,
        zone_data: ZoneData | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> bool:
        """
        Configure detection zones on the detector instance.

        Phase 6: Extracted from controller.setup_detector_zones()

        Args:
            zones_data: Preferred zone configuration input. If None, falls back to zone_data
            video_width: Preferred frame width. If None, falls back to width
            video_height: Preferred frame height. If None, falls back to height
            zone_data: Backward-compatible zone configuration parameter
            width: Backward-compatible frame width parameter
            height: Backward-compatible frame height parameter

        Returns:
            bool: True if zones were configured successfully
        """
        if not self.detector:
            log.warning("detector_service.configure_zones.no_detector")
            return False

        # Resolve preferred parameters while maintaining backward compatibility
        if legacy_dimensions:
            if len(legacy_dimensions) >= 1 and video_width is None:
                video_width = legacy_dimensions[0]
            if len(legacy_dimensions) >= 2 and video_height is None:
                video_height = legacy_dimensions[1]

        resolved_zone_data = zones_data if zones_data is not None else zone_data

        # Load zone data from project if not provided
        if resolved_zone_data is None:
            resolved_zone_data = self.project_manager.get_zone_data()

        # Use camera settings if dimensions not provided
        resolved_width = video_width if video_width is not None else width
        if resolved_width is None:
            resolved_width = self.settings.camera.desired_width

        resolved_height = video_height if video_height is not None else height
        if resolved_height is None:
            resolved_height = self.settings.camera.desired_height

        # Set zones on detector
        self.detector.set_zones(resolved_zone_data, resolved_width, resolved_height)
        log.info("detector_service.zones.configured", count=len(resolved_zone_data.roi_polygons))

        # Inform detector about aquarium region status
        has_aquarium = bool(resolved_zone_data and resolved_zone_data.polygon)
        self.detector.set_aquarium_region_defined(has_aquarium)
        log.info(
            "detector_service.aquarium_status.updated",
            defined=has_aquarium,
        )

        return True

    def update_tracking_parameters(
        self,
        params: dict[str, Any] | None = None,
        *,
        conf_threshold: float | None = None,
        nms_threshold: float | None = None,
        use_bytetrack: bool | None = None,
        track_threshold: float | None = None,
        match_threshold: float | None = None,
        track_buffer: int | None = None,
        max_center_distance: float | None = None,
        iou_threshold: float | None = None,
        reset_overrides: bool = False,
        scope: Literal["global", "project"] = "global",
    ) -> bool:
        """
        Update detector tracking parameters.

        Args:
            params: Dict of parameters to update
            conf_threshold: Confidence threshold override
            nms_threshold: NMS threshold override
            use_bytetrack: ByteTrack toggle override
            track_threshold: ByteTrack track threshold override
            match_threshold: ByteTrack match threshold override
            track_buffer: ByteTrack buffer override
            max_center_distance: Hybrid matching distance override
            iou_threshold: Hybrid matching IoU override
            reset_overrides: If True, reset overrides for the given scope
            scope: Whether the changes apply globally or only to the project

        Returns:
            bool: True if parameters were updated successfully
        """
        scope_normalized = scope or "global"
        if scope_normalized not in {"global", "project"}:
            raise ValueError(f"Unsupported calibration scope: {scope}")

        persist_global = scope_normalized == "global"
        params_dict: dict[str, Any] = dict(params or {})

        # Normalize parameter names
        if "confidence_threshold" in params_dict:
            params_dict["conf_threshold"] = params_dict.pop("confidence_threshold")

        if conf_threshold is not None:
            params_dict["conf_threshold"] = conf_threshold
        if nms_threshold is not None:
            params_dict["nms_threshold"] = nms_threshold
        if use_bytetrack is not None:
            params_dict["use_bytetrack"] = use_bytetrack
        if track_threshold is not None:
            params_dict["track_threshold"] = track_threshold
        if match_threshold is not None:
            params_dict["match_threshold"] = match_threshold
        if track_buffer is not None:
            params_dict["track_buffer"] = track_buffer
        if max_center_distance is not None:
            params_dict["max_center_distance"] = max_center_distance
        if iou_threshold is not None:
            params_dict["iou_threshold"] = iou_threshold

        # Validation helper
        def _validate_range(
            param_name: str, value: Any, min_val: float = 0.0, max_val: float = 1.0
        ):
            if value is not None:
                try:
                    val = float(value)
                    if val < min_val or val > max_val:
                        raise ValueError(
                            f"{param_name} deve estar entre {min_val} e {max_val}, recebido {val}"
                        )
                except (TypeError, ValueError) as e:
                    if isinstance(e, ValueError) and "deve estar entre" in str(e):
                        raise
                    raise ValueError(f"{param_name} deve ser um número válido")

        # Validate parameters
        _validate_range("conf_threshold", params_dict.get("conf_threshold"))
        _validate_range("nms_threshold", params_dict.get("nms_threshold"))
        _validate_range("track_threshold", params_dict.get("track_threshold"))
        _validate_range("match_threshold", params_dict.get("match_threshold"))
        _validate_range("iou_threshold", params_dict.get("iou_threshold"))

        if "track_buffer" in params_dict:
            try:
                if int(params_dict["track_buffer"]) < 1:
                    raise ValueError("track_buffer deve ser pelo menos 1")
            except (TypeError, ValueError):
                raise ValueError("track_buffer deve ser um número inteiro")

        plugin = self.detector.plugin if self.detector else None
        clear_project_overrides = scope_normalized == "project" and reset_overrides

        if clear_project_overrides:
            self._persist_project_detector_overrides({})
            reset_overrides = False
            defaults = self._get_current_global_thresholds()
            for key, value in defaults.items():
                params_dict.setdefault(key, value)

        if not plugin:
            current_defaults = self.get_detector_parameters()
            payload: dict[str, Any] = {}
            has_change = False

            keys = [
                "conf_threshold",
                "nms_threshold",
                "use_bytetrack",
                "track_threshold",
                "match_threshold",
                "track_buffer",
                "max_center_distance",
                "iou_threshold",
            ]
            for key in keys:
                new_val = params_dict.get(key)
                if new_val is not None and new_val != current_defaults.get(key):
                    payload[key] = new_val
                    has_change = True

            if not has_change and not clear_project_overrides:
                log.info("detector_service.update_params.no_changes")
                return True

            if persist_global:
                self._persist_global_detector_defaults(payload, reset=reset_overrides)

            if clear_project_overrides:
                return True

            self._persist_project_detector_overrides(payload)
            return True

        try:
            project_data = getattr(self.project_manager, "project_data", None)
            has_project_context = project_data is not None
            persist_project = (
                has_project_context
                and (scope_normalized == "project" or persist_global)
                and not clear_project_overrides
            )
            return self._apply_tracking_params_to_plugin(
                plugin,
                params_dict,
                persist_global=persist_global,
                persist_project=persist_project,
                reset_overrides=reset_overrides,
            )
        except Exception as e:
            log.error("detector_service.update_params.failed", error=str(e), exc_info=True)
            return False

    def _apply_tracking_params_to_plugin(
        self,
        plugin,
        params: dict,
        *,
        persist_global: bool,
        persist_project: bool,
        reset_overrides: bool,
    ) -> bool:
        """Apply tracking parameters to the plugin and persist configuration."""
        conf_val = params.get("conf_threshold")
        nms_val = params.get("nms_threshold")

        # Tracking params
        use_bt = params.get("use_bytetrack")
        track_val = params.get("track_threshold")
        match_val = params.get("match_threshold")
        buffer_val = params.get("track_buffer")
        dist_val = params.get("max_center_distance")
        iou_val = params.get("iou_threshold")

        # Update confidence threshold
        if conf_val is not None and hasattr(plugin, "conf_threshold"):
            plugin.conf_threshold = float(conf_val)
            log.info("detector_service.conf_threshold.updated", value=conf_val)

        # Update NMS threshold
        if nms_val is not None and hasattr(plugin, "nms_threshold"):
            plugin.nms_threshold = float(nms_val)
            log.info("detector_service.nms_threshold.updated", value=nms_val)

        # Update ByteTrack toggle in settings (Detector reads from it)
        if use_bt is not None:
            if hasattr(self.settings, "tracking"):
                self.settings.tracking.use_bytetrack = bool(use_bt)
                log.info("detector_service.use_bytetrack.updated", value=use_bt)

        # Update thresholds in settings (Detector reads from it)
        if hasattr(self.settings, "bytetrack"):
            bt = self.settings.bytetrack
            if track_val is not None:
                bt.track_threshold = float(track_val)
            if match_val is not None:
                bt.match_threshold = float(match_val)
            if buffer_val is not None:
                bt.track_buffer = int(buffer_val)
            if dist_val is not None:
                bt.max_center_distance = float(dist_val)
            if iou_val is not None:
                bt.iou_threshold = float(iou_val)

            log.info(
                "detector_service.tracking_settings.updated",
                count=sum(
                    1
                    for v in [track_val, match_val, buffer_val, dist_val, iou_val]
                    if v is not None
                ),
            )

        # Build detector config for persistence
        detector_config: dict[str, Any] = {}
        if conf_val is not None:
            detector_config["conf_threshold"] = float(conf_val)
        if nms_val is not None:
            detector_config["nms_threshold"] = float(nms_val)
        if use_bt is not None:
            detector_config["use_bytetrack"] = bool(use_bt)
        if track_val is not None:
            detector_config["track_threshold"] = float(track_val)
        if match_val is not None:
            detector_config["match_threshold"] = float(match_val)
        if buffer_val is not None:
            detector_config["track_buffer"] = int(buffer_val)
        if dist_val is not None:
            detector_config["max_center_distance"] = float(dist_val)
        if iou_val is not None:
            detector_config["iou_threshold"] = float(iou_val)

        if persist_global:
            self._persist_global_detector_defaults(detector_config, reset=reset_overrides)
        elif reset_overrides:
            log.info("detector_service.params.project_reset_applied", config=detector_config)

        if persist_project:
            save_success = self._persist_project_detector_overrides(detector_config)
            if save_success:
                log.info("detector_service.params.saved_to_project", config=detector_config)
            else:
                log.warning("detector_service.params.save_to_project_failed")

        return True

    def reset_tracking_state(self) -> None:
        """
        Reset tracker state between videos.

        Phase 6: Extracted from controller logic
        """
        if not self.detector:
            log.debug("detector_service.reset_tracking.no_detector")
            return

        try:
            self.detector.reset_tracking_state()
            log.info("detector_service.reset_tracking.success")
        except Exception as e:
            log.warning("detector_service.reset_tracking.failed", error=str(e), exc_info=True)

    def set_single_subject_mode(self, enabled: bool) -> None:
        """
        Configure single-subject tracking mode.

        Phase 6: Extracted from controller._configure_single_subject_tracker()

        Args:
            enabled: Whether to enable single-subject mode
        """
        if not self.detector:
            log.debug("detector_service.single_subject.no_detector")
            return

        try:
            self.detector.set_single_subject_mode(bool(enabled))
            log.info("detector_service.single_subject.configured", enabled=enabled)
        except Exception as e:
            log.error("detector_service.single_subject.failed", error=str(e), enabled=enabled)

    def get_detector_parameters(self) -> dict[str, Any]:
        """
        Get current detector thresholds, falling back to saved or default values.

        Phase 6: Extracted from controller.get_current_detector_parameters()

        Returns:
            dict: Current detector parameters
        """
        params: dict[str, Any] = {
            "conf_threshold": self.settings.yolo_model.confidence_threshold,
            "nms_threshold": self.settings.yolo_model.nms_threshold,
            "use_bytetrack": True,
            "track_threshold": DEFAULT_TRACK_THRESHOLD,
            "match_threshold": DEFAULT_MATCH_THRESHOLD,
            "track_buffer": 90,
            "max_center_distance": 200.0,
            "iou_threshold": 0.1,
        }

        # Sync from settings
        if hasattr(self.settings, "tracking"):
            params["use_bytetrack"] = self.settings.tracking.use_bytetrack

        if hasattr(self.settings, "bytetrack"):
            bt = self.settings.bytetrack
            params.update(
                {
                    "track_threshold": bt.track_threshold,
                    "match_threshold": bt.match_threshold,
                    "track_buffer": bt.track_buffer,
                    "max_center_distance": bt.max_center_distance,
                    "iou_threshold": bt.iou_threshold,
                }
            )

        # Override from active plugin if available
        plugin = self.detector.plugin if self.detector else None
        if plugin:
            params["conf_threshold"] = getattr(plugin, "conf_threshold", params["conf_threshold"])
            params["nms_threshold"] = getattr(plugin, "nms_threshold", params["nms_threshold"])

        # Check for project-specific overrides
        project_data = getattr(self.project_manager, "project_data", {})
        if project_data:
            detector_state = project_data.get("detector_state", {})
            for key in params.keys():
                val = detector_state.get(key)
                if val is not None:
                    try:
                        if key == "use_bytetrack":
                            params[key] = bool(val)
                        elif key == "track_buffer":
                            params[key] = int(val)
                        else:
                            params[key] = float(val)
                    except (TypeError, ValueError):
                        log.warning(
                            "detector_service.get_params.invalid_override", key=key, value=val
                        )

        return params

    def get_factory_detector_parameters(self) -> dict[str, Any]:
        """
        Get factory default detector thresholds without any overrides.

        Phase 6: Extracted from controller.get_factory_detector_parameters()

        Returns:
            dict: Factory default parameters
        """
        return {
            "conf_threshold": 0.25,
            "nms_threshold": 0.45,
            "use_bytetrack": True,
            "track_threshold": 0.25,
            "match_threshold": 0.80,
            "track_buffer": 90,
            "max_center_distance": 200.0,
            "iou_threshold": 0.1,
        }

    def restore_detector_settings(self, saved_detector_config: dict) -> None:
        """
        Restore detector settings from saved configuration.

        Phase 6: Extracted from controller._restore_detector_settings()

        Args:
            saved_detector_config: Saved detector configuration from project
        """
        if not saved_detector_config:
            return

        log.info("detector_service.restore_settings.start", config=saved_detector_config)

        # Apply values to settings object first
        if "conf_threshold" in saved_detector_config:
            self.settings.yolo_model.confidence_threshold = float(
                saved_detector_config["conf_threshold"]
            )
        if "nms_threshold" in saved_detector_config:
            self.settings.yolo_model.nms_threshold = float(saved_detector_config["nms_threshold"])

        if "use_bytetrack" in saved_detector_config:
            self.settings.tracking.use_bytetrack = bool(saved_detector_config["use_bytetrack"])

        if hasattr(self.settings, "bytetrack"):
            bt = self.settings.bytetrack
            if "track_threshold" in saved_detector_config:
                bt.track_threshold = float(saved_detector_config["track_threshold"])
            if "match_threshold" in saved_detector_config:
                bt.match_threshold = float(saved_detector_config["match_threshold"])
            if "track_buffer" in saved_detector_config:
                bt.track_buffer = int(saved_detector_config["track_buffer"])
            if "max_center_distance" in saved_detector_config:
                bt.max_center_distance = float(saved_detector_config["max_center_distance"])
            if "iou_threshold" in saved_detector_config:
                bt.iou_threshold = float(saved_detector_config["iou_threshold"])

        # If detector is active, sync plugin
        if self.detector and self.detector.plugin:
            plugin = self.detector.plugin
            if "conf_threshold" in saved_detector_config and hasattr(plugin, "conf_threshold"):
                plugin.conf_threshold = float(saved_detector_config["conf_threshold"])
            if "nms_threshold" in saved_detector_config and hasattr(plugin, "nms_threshold"):
                plugin.nms_threshold = float(saved_detector_config["nms_threshold"])

        log.info("detector_service.restore_settings.success")

    # === Private Helper Methods ===

    def _build_detector_config(self, plugin: DetectorPlugin, use_openvino: bool) -> dict:
        """
        Build detector configuration dict for persistence.

        Args:
            plugin: Detector plugin instance
            use_openvino: Whether OpenVINO is being used

        Returns:
            dict: Detector configuration
        """
        detector_config = {
            "plugin_name": ("OpenVINO" if use_openvino else "YOLO (Ultralytics)"),
            "conf_threshold": plugin.conf_threshold,
            "nms_threshold": plugin.nms_threshold,
            "context": getattr(plugin, "_context", "tracking"),
        }

        # Add ByteTrack parameters from settings
        detector_config["use_bytetrack"] = self.settings.tracking.use_bytetrack
        if hasattr(self.settings, "bytetrack"):
            bt = self.settings.bytetrack
            detector_config.update(
                {
                    "track_threshold": bt.track_threshold,
                    "match_threshold": bt.match_threshold,
                    "track_buffer": bt.track_buffer,
                    "max_center_distance": bt.max_center_distance,
                    "iou_threshold": bt.iou_threshold,
                }
            )

        return detector_config

    def _persist_global_detector_defaults(
        self,
        detector_config: dict[str, Any],
        *,
        reset: bool = False,
    ) -> None:
        """
        Persist detector defaults to global settings.

        Args:
            detector_config: Configuration to persist
            reset: If True, reset to factory defaults
        """
        if reset:
            factory = self.get_factory_detector_parameters()
            self.settings.yolo_model.confidence_threshold = factory["conf_threshold"]
            self.settings.yolo_model.nms_threshold = factory["nms_threshold"]
            self.settings.tracking.use_bytetrack = factory["use_bytetrack"]
            if hasattr(self.settings, "bytetrack"):
                bt = self.settings.bytetrack
                bt.track_threshold = factory["track_threshold"]
                bt.match_threshold = factory["match_threshold"]
                bt.track_buffer = factory["track_buffer"]
                bt.max_center_distance = factory["max_center_distance"]
                bt.iou_threshold = factory["iou_threshold"]
            log.info("detector_service.persist.reset_to_factory")
        else:
            if "conf_threshold" in detector_config:
                self.settings.yolo_model.confidence_threshold = float(
                    detector_config["conf_threshold"]
                )
            if "nms_threshold" in detector_config:
                self.settings.yolo_model.nms_threshold = float(detector_config["nms_threshold"])
            if "use_bytetrack" in detector_config:
                self.settings.tracking.use_bytetrack = bool(detector_config["use_bytetrack"])

            if hasattr(self.settings, "bytetrack"):
                bt = self.settings.bytetrack
                if "track_threshold" in detector_config:
                    bt.track_threshold = float(detector_config["track_threshold"])
                if "match_threshold" in detector_config:
                    bt.match_threshold = float(detector_config["match_threshold"])
                if "track_buffer" in detector_config:
                    bt.track_buffer = int(detector_config["track_buffer"])
                if "max_center_distance" in detector_config:
                    bt.max_center_distance = float(detector_config["max_center_distance"])
                if "iou_threshold" in detector_config:
                    bt.iou_threshold = float(detector_config["iou_threshold"])

            log.info("detector_service.persist.overrides_applied", config=detector_config)

        # Force save to config.local.yaml so changes persist across restarts
        try:
            save_settings(self.settings)
        except Exception as e:
            log.error("detector_service.persist_global.save_failed", error=str(e))

    def _persist_project_detector_overrides(self, detector_config: dict[str, Any]) -> bool:
        """Persist detector overrides to the active project, if available."""
        if not hasattr(self.project_manager, "save_detector_state"):
            return False

        try:
            return bool(self.project_manager.save_detector_state(detector_config))
        except Exception:
            log.warning(
                "detector_service.project_overrides.persist_failed",
                config=detector_config,
                exc_info=True,
            )
            return False

    def _get_current_global_thresholds(self) -> dict[str, Any]:
        """Return the thresholds currently configured in global settings."""
        res = {
            "conf_threshold": self.settings.yolo_model.confidence_threshold,
            "nms_threshold": self.settings.yolo_model.nms_threshold,
            "use_bytetrack": self.settings.tracking.use_bytetrack,
        }
        if hasattr(self.settings, "bytetrack"):
            bt = self.settings.bytetrack
            res.update(
                {
                    "track_threshold": bt.track_threshold,
                    "match_threshold": bt.match_threshold,
                    "track_buffer": bt.track_buffer,
                    "max_center_distance": bt.max_center_distance,
                    "iou_threshold": bt.iou_threshold,
                }
            )
        return res

    def _resolve_single_subject_tracker_preference(self, project_type: str | None) -> bool | None:
        """
        Resolve single-subject tracker preference from project config.

        Args:
            project_type: Project type (live, pre-recorded, single-video)

        Returns:
            bool | None: Tracker preference or None if not set
        """
        project_data = getattr(self.project_manager, "project_data", {}) or {}

        if not project_data:
            # No project data available, check project type defaults
            if project_type == "single-video":
                return True
            return None

        # Newer project files keep tracking preferences inside the tracking stanza
        tracker_section = project_data.get("tracking")

        pref = project_data.get("use_single_subject_tracker")
        if pref is None and isinstance(tracker_section, dict):
            pref = tracker_section.get("use_single_subject_tracker")

        if pref is None:
            calibration = project_data.get("calibration") or {}
            animals = calibration.get("animals_per_aquarium")
            if animals is not None:
                try:
                    pref = int(animals) == 1
                except (TypeError, ValueError):
                    pref = None

        if pref is not None:
            return bool(pref)

        # Default based on project type
        if project_type == "single-video":
            return True

        return None

    def _validate_model_classes(self, plugin_instance: DetectorPlugin, model_path: str) -> None:
        """
        Validate that model has expected classes for ZebTrack-AI.

        Args:
            plugin_instance: The instantiated detector plugin
            model_path: Path to the model (for logging)

        Raises:
            ValueError: If model is missing required classes
        """
        plugin_classes = getattr(plugin_instance, "class_names", {})

        if not plugin_classes:
            log.warning(
                "detector_service.validate_classes.no_classes",
                model_path=model_path,
                message="Plugin has no class_names attribute. Validation skipped.",
            )
            return

        # Define expected names (case-insensitive)
        aquarium_names = ["aqua", "aquarium", "tank", "agua"]
        animal_names = ["zebrafish", "fish", "peixe"]

        # Check what we have
        has_aquarium = False
        has_animal = False

        for class_id, name in plugin_classes.items():
            name_lower = name.lower()
            if name_lower in aquarium_names:
                has_aquarium = True
            if name_lower in animal_names:
                has_animal = True

        # Logic:
        # 1. We MUST have an animal class (unless it's a purely aquarium segmentation model,
        #    but here we are likely validating the 'det' model).
        # 2. We ideally want an aquarium class, but for 'Single Object' models (best_oi.pt),
        #    it might be missing. We should ALLOW this if an animal class is present.

        if not has_animal and not has_aquarium:
            # Worst case: neither known class found
            log.warning(
                "detector_service.validate_classes.unknown_classes",
                plugin_classes=plugin_classes,
                model_path=model_path,
                message="No recognized aquarium or animal classes found. Tracking may fail.",
            )
            # We don't raise here to allow custom models with weird names,
            # but we log a strong warning.
            return

        if not has_animal:
            # If we are loading the ANIMAL detection model, we really need an animal class.
            # However, maybe the user is using a generic model (person, etc.)?
            # Let's just warn.
            log.warning(
                "detector_service.validate_classes.no_animal_class",
                plugin_classes=plugin_classes,
                model_path=model_path,
                message="Model does not seem to have a 'zebrafish' class.",
            )

        log.info(
            "detector_service.validate_classes.success",
            model_path=model_path,
            plugin_classes=plugin_classes,
            has_aquarium=has_aquarium,
            has_animal=has_animal,
        )
