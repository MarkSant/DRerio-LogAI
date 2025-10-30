"""
Detector Service for ZebTrack-AI.

Phase 6: Service layer for detector and zone management.

Handles detector initialization, zone configuration, tracking parameter
updates, and plugin context management operations.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

import structlog

from zebtrack.core.detector import Detector, ZoneData
from zebtrack.utils import IntegrityError

if TYPE_CHECKING:
    from zebtrack.core.model_service import ModelService
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.weight_manager import WeightManager
    from zebtrack.plugins.base import DetectorPlugin
    from zebtrack.settings import Settings

log = structlog.get_logger()

# Default thresholds
DEFAULT_TRACK_THRESHOLD = 0.25
DEFAULT_MATCH_THRESHOLD = 0.15


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
        self, zone_data: ZoneData | None = None, width: int | None = None, height: int | None = None
    ) -> bool:
        """
        Configure detection zones on the detector instance.

        Phase 6: Extracted from controller.setup_detector_zones()

        Args:
            zone_data: Zone configuration. If None, loads from project
            width: Frame width. If None, uses camera settings
            height: Frame height. If None, uses camera settings

        Returns:
            bool: True if zones were configured successfully
        """
        if not self.detector:
            log.warning("detector_service.configure_zones.no_detector")
            return False

        # Load zone data from project if not provided
        if zone_data is None:
            zone_data = self.project_manager.get_zone_data()

        # Use camera settings if dimensions not provided
        if width is None:
            width = self.settings.camera.desired_width
        if height is None:
            height = self.settings.camera.desired_height

        # Set zones on detector
        self.detector.set_zones(zone_data, width, height)
        log.info("detector_service.zones.configured", count=len(zone_data.roi_polygons))

        # Inform plugin about aquarium region status
        plugin = getattr(self.detector, "plugin", None)
        if plugin and hasattr(plugin, "set_aquarium_region_defined"):
            has_aquarium = bool(zone_data and zone_data.polygon)
            plugin.set_aquarium_region_defined(has_aquarium)
            log.info(
                "detector_service.aquarium_status.updated",
                defined=has_aquarium,
                plugin=plugin.get_name() if hasattr(plugin, "get_name") else "unknown",
            )

        return True

    def update_tracking_parameters(
        self,
        params: dict[str, float] | None = None,
        *,
        conf_threshold: float | None = None,
        nms_threshold: float | None = None,
        track_threshold: float | None = None,
        match_threshold: float | None = None,
        reset_overrides: bool = False,
        scope: Literal["global", "project"] = "global",
    ) -> bool:
        """
        Update detector tracking parameters.

        Args:
            params: Dict of parameters to update
            conf_threshold: Confidence threshold override
            nms_threshold: NMS threshold override
            track_threshold: ByteTrack track threshold override
            match_threshold: ByteTrack match threshold override
            reset_overrides: If True, reset overrides for the given scope
            scope: Whether the changes apply globally or only to the project

        Returns:
            bool: True if parameters were updated successfully
        """
        scope_normalized = scope or "global"
        if scope_normalized not in {"global", "project"}:
            raise ValueError(f"Unsupported calibration scope: {scope}")

        persist_global = scope_normalized == "global"
        params_dict: dict[str, float] = dict(params or {})

        # Normalize parameter names (accept both long and short forms)
        if "confidence_threshold" in params_dict:
            params_dict["conf_threshold"] = params_dict.pop("confidence_threshold")

        if conf_threshold is not None:
            params_dict["conf_threshold"] = conf_threshold
        if nms_threshold is not None:
            params_dict["nms_threshold"] = nms_threshold
        if track_threshold is not None:
            params_dict["track_threshold"] = track_threshold
        if match_threshold is not None:
            params_dict["match_threshold"] = match_threshold

        # Validation helper
        def _validate(param_name: str, value: float | None):
            if value is not None and (value < 0.0 or value > 1.0):
                raise ValueError(f"{param_name} must be between 0 and 1, got {value}")

        # Validate all parameters
        _validate("conf_threshold", params_dict.get("conf_threshold"))
        _validate("nms_threshold", params_dict.get("nms_threshold"))
        _validate("track_threshold", params_dict.get("track_threshold"))
        _validate("match_threshold", params_dict.get("match_threshold"))

        plugin = self.detector.plugin if self.detector else None
        clear_project_overrides = scope_normalized == "project" and reset_overrides

        if clear_project_overrides:
            self._persist_project_detector_overrides({})
            reset_overrides = False  # Avoid resetting global defaults downstream
            defaults = self._get_current_global_thresholds()
            for key, value in defaults.items():
                params_dict.setdefault(key, value)

        if not plugin:
            current_defaults = self.get_detector_parameters()
            payload: dict[str, float] = {}
            has_change = False

            for key in ["conf_threshold", "nms_threshold", "track_threshold", "match_threshold"]:
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
        track_val = params.get("track_threshold")
        match_val = params.get("match_threshold")

        # Update confidence threshold
        if conf_val is not None and hasattr(plugin, "conf_threshold"):
            plugin.conf_threshold = float(conf_val)
            log.info("detector_service.conf_threshold.updated", value=conf_val)

        # Update NMS threshold
        if nms_val is not None and hasattr(plugin, "nms_threshold"):
            plugin.nms_threshold = float(nms_val)
            log.info("detector_service.nms_threshold.updated", value=nms_val)

        # Update ByteTrack thresholds
        if hasattr(plugin, "set_tracking_parameters"):
            plugin.set_tracking_parameters(track_threshold=track_val, match_threshold=match_val)
            log.info(
                "detector_service.tracking_params.updated",
                track_threshold=track_val,
                match_threshold=match_val,
            )

        # Build detector config for persistence
        detector_config: dict[str, float] = {}
        if conf_val is not None:
            detector_config["conf_threshold"] = float(conf_val)
        if nms_val is not None:
            detector_config["nms_threshold"] = float(nms_val)
        if track_val is not None:
            detector_config["track_threshold"] = float(track_val)
        if match_val is not None:
            detector_config["match_threshold"] = float(match_val)

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
        except AttributeError:
            log.debug(
                "detector_service.single_subject.unavailable",
                plugin=getattr(self.detector, "plugin", "unknown"),
            )

    def get_detector_parameters(self) -> dict[str, float]:
        """
        Get current detector thresholds, falling back to saved or default values.

        Phase 6: Extracted from controller.get_current_detector_parameters()

        Returns:
            dict: Current detector parameters
        """
        # If detector with plugin exists, read current values from plugin
        plugin = self.detector.plugin if self.detector else None
        if plugin:
            params = {
                "conf_threshold": getattr(
                    plugin, "conf_threshold", self.settings.yolo_model.confidence_threshold
                ),
                "nms_threshold": getattr(
                    plugin, "nms_threshold", self.settings.yolo_model.nms_threshold
                ),
                "track_threshold": getattr(plugin, "track_threshold", DEFAULT_TRACK_THRESHOLD),
                "match_threshold": getattr(plugin, "match_threshold", DEFAULT_MATCH_THRESHOLD),
            }
            return params

        # No detector - fall back to settings and project data
        track_default = DEFAULT_TRACK_THRESHOLD
        match_default = DEFAULT_MATCH_THRESHOLD

        params = {
            "conf_threshold": self.settings.yolo_model.confidence_threshold,
            "nms_threshold": self.settings.yolo_model.nms_threshold,
            "track_threshold": track_default,
            "match_threshold": match_default,
        }

        # Try to get ByteTrack defaults from settings
        try:
            if hasattr(self.settings, "bytetrack"):
                bt_track = getattr(self.settings.bytetrack, "track_threshold", None)
                bt_match = getattr(self.settings.bytetrack, "match_threshold", None)
                if bt_track is not None:
                    params["track_threshold"] = float(bt_track)
                if bt_match is not None:
                    params["match_threshold"] = float(bt_match)
        except Exception:
            log.debug("detector_service.get_params.bytetrack_fallback", exc_info=True)

        # Check for project-specific overrides
        project_data = getattr(self.project_manager, "project_data", {})
        if project_data:
            detector_state = project_data.get("detector_state", {})
            for key in ["conf_threshold", "nms_threshold", "track_threshold", "match_threshold"]:
                val = detector_state.get(key)
                if val is not None:
                    try:
                        params[key] = float(val)
                    except (TypeError, ValueError):
                        log.warning(
                            "detector_service.get_params.invalid_override", key=key, value=val
                        )

        return params

    def get_factory_detector_parameters(self) -> dict[str, float]:
        """
        Get factory default detector thresholds without any overrides.

        Phase 6: Extracted from controller.get_factory_detector_parameters()

        Returns:
            dict: Factory default parameters
        """
        try:
            conf_default = float(self.settings.yolo_model.confidence_threshold)
            nms_default = float(self.settings.yolo_model.nms_threshold)
        except Exception:
            log.warning("detector_service.factory_params.fallback", exc_info=True)
            conf_default = 0.25
            nms_default = 0.45

        track_default = DEFAULT_TRACK_THRESHOLD
        match_default = DEFAULT_MATCH_THRESHOLD

        try:
            if hasattr(self.settings, "bytetrack"):
                bt_track = getattr(self.settings.bytetrack, "track_threshold", None)
                bt_match = getattr(self.settings.bytetrack, "match_threshold", None)
                if bt_track is not None:
                    track_default = float(bt_track)
                if bt_match is not None:
                    match_default = float(bt_match)
        except Exception:
            log.debug("detector_service.factory_params.bytetrack_fallback", exc_info=True)

        return {
            "conf_threshold": conf_default,
            "nms_threshold": nms_default,
            "track_threshold": track_default,
            "match_threshold": match_default,
        }

    def restore_detector_settings(self, saved_detector_config: dict) -> None:
        """
        Restore detector settings from saved configuration.

        Phase 6: Extracted from controller._restore_detector_settings()

        Args:
            saved_detector_config: Saved detector configuration from project
        """
        if not saved_detector_config or not self.detector:
            return

        log.info(
            "detector_service.restore_settings.start",
            config=saved_detector_config,
        )

        plugin = self.detector.plugin
        settings_changed = False

        # Restore confidence threshold
        saved_conf = saved_detector_config.get("confidence_threshold")
        if saved_conf is not None and hasattr(plugin, "conf_threshold"):
            try:
                plugin.conf_threshold = float(saved_conf)
                settings_changed = True
                log.info("detector_service.restore.conf_threshold", value=saved_conf)
            except (TypeError, ValueError) as e:
                log.warning("detector_service.restore.conf_invalid", error=str(e))

        # Restore NMS threshold
        saved_nms = saved_detector_config.get("nms_threshold")
        if saved_nms is not None and hasattr(plugin, "nms_threshold"):
            try:
                plugin.nms_threshold = float(saved_nms)
                settings_changed = True
                log.info("detector_service.restore.nms_threshold", value=saved_nms)
            except (TypeError, ValueError) as e:
                log.warning("detector_service.restore.nms_invalid", error=str(e))

        # Restore ByteTrack parameters
        saved_track = saved_detector_config.get("track_threshold")
        saved_match = saved_detector_config.get("match_threshold")
        if hasattr(plugin, "set_tracking_parameters"):
            try:
                plugin.set_tracking_parameters(
                    track_threshold=saved_track, match_threshold=saved_match
                )
                settings_changed = True
                log.info(
                    "detector_service.restore.tracking_params",
                    track=saved_track,
                    match=saved_match,
                )
            except Exception as e:
                log.warning("detector_service.restore.tracking_params_failed", error=str(e))

        if settings_changed:
            log.info("detector_service.restore_settings.success")
        else:
            log.debug("detector_service.restore_settings.no_changes")

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
            "confidence_threshold": plugin.conf_threshold,
            "nms_threshold": plugin.nms_threshold,
            "context": getattr(plugin, "_context", "tracking"),
        }

        # Add ByteTrack parameters if available
        if hasattr(plugin, "track_threshold"):
            track_val = getattr(plugin, "track_threshold", None)
            if track_val is not None:
                detector_config["track_threshold"] = float(track_val)

        if hasattr(plugin, "match_threshold"):
            match_val = getattr(plugin, "match_threshold", None)
            if match_val is not None:
                detector_config["match_threshold"] = float(match_val)

        # Use get_context_info if available
        if hasattr(plugin, "get_context_info"):
            context_info = plugin.get_context_info()
            detector_config["context"] = context_info.get("context", "tracking")

        return detector_config

    def _persist_global_detector_defaults(
        self,
        detector_config: dict[str, float],
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
            # Reset to factory defaults
            factory = self.get_factory_detector_parameters()
            self.settings.yolo_model.confidence_threshold = factory["conf_threshold"]
            self.settings.yolo_model.nms_threshold = factory["nms_threshold"]
            if hasattr(self.settings, "bytetrack"):
                self.settings.bytetrack.track_threshold = factory["track_threshold"]
                self.settings.bytetrack.match_threshold = factory["match_threshold"]
            log.info("detector_service.persist.reset_to_factory")
        else:
            # Apply overrides
            conf_val = detector_config.get("conf_threshold")
            nms_val = detector_config.get("nms_threshold")
            track_val = detector_config.get("track_threshold")
            match_val = detector_config.get("match_threshold")

            if conf_val is not None:
                self.settings.yolo_model.confidence_threshold = float(conf_val)
            if nms_val is not None:
                self.settings.yolo_model.nms_threshold = float(nms_val)

            if hasattr(self.settings, "bytetrack"):
                if track_val is not None:
                    self.settings.bytetrack.track_threshold = float(track_val)
                if match_val is not None:
                    self.settings.bytetrack.match_threshold = float(match_val)

            log.info("detector_service.persist.overrides_applied", config=detector_config)

    def _persist_project_detector_overrides(self, detector_config: dict[str, float]) -> bool:
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

    def _get_current_global_thresholds(self) -> dict[str, float]:
        """Return the thresholds currently configured in global settings."""
        try:
            conf = float(getattr(self.settings.yolo_model, "confidence_threshold", 0.25))
        except Exception:
            log.debug("detector_service.global_thresholds.conf_fallback", exc_info=True)
            conf = 0.25

        try:
            nms = float(getattr(self.settings.yolo_model, "nms_threshold", 0.45))
        except Exception:
            log.debug("detector_service.global_thresholds.nms_fallback", exc_info=True)
            nms = 0.45

        track = DEFAULT_TRACK_THRESHOLD
        match = DEFAULT_MATCH_THRESHOLD
        try:
            if hasattr(self.settings, "bytetrack"):
                track = float(getattr(self.settings.bytetrack, "track_threshold", track))
                match = float(getattr(self.settings.bytetrack, "match_threshold", match))
        except Exception:
            log.debug("detector_service.global_thresholds.bytetrack_fallback", exc_info=True)

        return {
            "conf_threshold": conf,
            "nms_threshold": nms,
            "track_threshold": track,
            "match_threshold": match,
        }

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
