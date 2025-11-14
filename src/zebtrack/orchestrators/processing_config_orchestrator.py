"""Processing configuration orchestration logic extracted from MainViewModel.

Sprint 31 - Extracted to reduce MainViewModel complexity.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

import structlog

from zebtrack.core.processing_mode import ProcessingMode, ProcessingReport

if TYPE_CHECKING:
    from zebtrack.core.main_view_model import MainViewModel

log = structlog.get_logger()


class ProcessingConfigOrchestrator:
    """Orchestrates processing configuration and mode management.

    Extracted from MainViewModel in Sprint 31 to reduce its size.
    Maintains reference to MainViewModel for delegation during gradual extraction.

    This class handles:
    - Processing mode determination (SINGLE_SUBJECT vs MULTI_TRACK)
    - Processing mode publication to UI
    - Single-animal mode resolution from config
    - Single-subject tracker preference resolution
    - Processing intervals configuration
    - Temporary mode context management
    """

    def __init__(self, main_view_model: MainViewModel):
        """Initialize with MainViewModel reference.

        Args:
            main_view_model: Reference to MainViewModel for delegation
        """
        self.main_view_model = main_view_model

        # Cache frequently used attributes from MainViewModel
        self.settings = main_view_model.settings
        self.project_manager = main_view_model.project_manager
        self.detector_service = main_view_model.detector_service
        self.detector_coordinator = main_view_model.detector_coordinator
        self.ui_state_controller = main_view_model.ui_state_controller

        # Internal state
        self._active_processing_mode = ProcessingMode.MULTI_TRACK

    def _determine_processing_mode(self) -> ProcessingMode:
        """Inspect current detector/settings state to infer active mode."""
        detector = getattr(self.main_view_model, "detector", None)
        if detector and hasattr(detector, "is_single_subject_mode"):
            try:
                if detector.is_single_subject_mode():
                    return ProcessingMode.SINGLE_SUBJECT
            except Exception:  # pragma: no cover - defensive telemetry
                log.warning(
                    "controller.processing_mode.detector_probe_failed",
                    exc_info=True,
                )

        try:
            use_single = bool(self.settings.tracking.use_single_subject_tracker)
            log.info(
                "controller.determine_processing_mode",
                use_single_subject_tracker=use_single,
                result="SINGLE_SUBJECT" if use_single else "MULTI_TRACK",
            )
            if use_single:
                return ProcessingMode.SINGLE_SUBJECT
        except AttributeError:  # pragma: no cover - optional settings
            # AttributeError occurs when video_processing settings don't exist.
            # This is expected behavior - fall through to default MULTI_TRACK mode.
            pass

        return ProcessingMode.MULTI_TRACK

    def _publish_processing_mode(
        self,
        *,
        source: str,
        force: bool = False,
        mode_override: ProcessingMode | None = None,
    ) -> ProcessingReport:
        """Notify the GUI about the current processing mode when it changes."""
        mode = mode_override or self._determine_processing_mode()
        if not force and mode == getattr(self, "_active_processing_mode", None):
            return ProcessingReport(mode=mode, source=source)

        self._active_processing_mode = mode
        report = ProcessingReport(mode=mode, source=source)
        view = getattr(self.main_view_model, "view", None)
        if view and hasattr(view, "update_processing_mode"):
            self.ui_state_controller._schedule_on_ui(view.update_processing_mode, report)
        return report

    def _resolve_single_animal_mode(self, single_video_config: dict | None) -> bool | None:
        """Derive whether single-animal tracking mode should be active."""

        def _coerce_to_int(value):
            if value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        if single_video_config:
            count = _coerce_to_int(single_video_config.get("animals_per_aquarium"))
            if count is not None:
                enabled = count == 1
                log.debug(
                    "controller.single_animal_mode.resolved_single_video",
                    animals_per_aquarium=count,
                    enabled=enabled,
                )
                return enabled

        project_data = getattr(self.project_manager, "project_data", {}) or {}
        calibration = project_data.get("calibration") or {}
        count = _coerce_to_int(calibration.get("animals_per_aquarium"))
        if count is not None:
            enabled = count == 1
            log.debug(
                "controller.single_animal_mode.resolved_project",
                animals_per_aquarium=count,
                enabled=enabled,
            )
            return enabled

        return None

    def _resolve_single_subject_tracker_preference(
        self, single_video_config: dict | None
    ) -> bool | None:
        """
        Resolve single-subject tracker preference from project or single video config.

        Args:
            single_video_config: Optional single video configuration dict

        Returns:
            bool | None: Tracker preference or None if not set
        """
        log.info(
            "controller.resolve_tracker.entry",
            has_config=single_video_config is not None,
            config_keys=list(single_video_config.keys()) if single_video_config else [],
        )

        # Check directly in single_video_config first
        if single_video_config:
            # Explicit use_single_subject_tracker takes priority
            if "use_single_subject_tracker" in single_video_config:
                pref = bool(single_video_config["use_single_subject_tracker"])
                log.info(
                    "controller.resolve_tracker.explicit",
                    use_single_subject=pref,
                    source="single_video_config",
                )
                return pref

            # Derive from animals_per_aquarium
            animals_per_aquarium = single_video_config.get("animals_per_aquarium")
            if animals_per_aquarium is not None:
                pref = int(animals_per_aquarium) == 1
                log.info(
                    "controller.resolve_tracker.from_animals",
                    use_single_subject=pref,
                    animals_per_aquarium=animals_per_aquarium,
                    source="single_video_config",
                )
                return pref

        # Try to get project type from single video config or project manager
        project_type = None
        if single_video_config:
            project_type = single_video_config.get("project_type")

        if not project_type:
            project_data = getattr(self.project_manager, "project_data", {})
            if project_data:
                project_type = project_data.get("project_type")

        # Delegate to detector service
        return self.detector_service._resolve_single_subject_tracker_preference(project_type)

    def _configure_single_subject_tracker(self, enabled: bool) -> None:
        """
        Configure single-subject tracking mode.

        Sprint 7: Delegates to DetectorCoordinator.
        """
        self.detector_coordinator.set_single_subject_mode(bool(enabled))
        self._publish_processing_mode(
            source="tracker_configuration",
            force=True,
        )

    def _determine_processing_intervals(self, single_video_config: dict | None) -> tuple[int, int]:
        analysis_interval_frames = 10
        display_interval_frames = 10

        if single_video_config:
            analysis_interval_frames = single_video_config.get(
                "analysis_interval_frames", analysis_interval_frames
            )
            display_interval_frames = single_video_config.get(
                "display_interval_frames", display_interval_frames
            )
            log.info(
                "controller.processing.intervals_single_video",
                analysis_interval=analysis_interval_frames,
                display_interval=display_interval_frames,
                config_keys=list(single_video_config.keys()),
                animals_per_aquarium=single_video_config.get("animals_per_aquarium"),
                use_single_subject_tracker=single_video_config.get("use_single_subject_tracker"),
            )
        else:
            project_data = getattr(self.project_manager, "project_data", {}) or {}
            analysis_interval_frames = project_data.get(
                "analysis_interval_frames", analysis_interval_frames
            )
            display_interval_frames = project_data.get(
                "display_interval_frames", display_interval_frames
            )

        return int(analysis_interval_frames), int(display_interval_frames)

    @contextmanager
    def _temporary_single_animal_mode(self, single_video_config: dict | None) -> Iterator[bool]:
        log.info(
            "controller.temporary_mode.entry",
            has_config=single_video_config is not None,
            config_keys=list(single_video_config.keys()) if single_video_config else [],
        )

        previous_mode = self.settings.video_processing.single_animal_per_aquarium
        resolved_mode = self._resolve_single_animal_mode(single_video_config)

        previous_tracker_pref = self.settings.tracking.use_single_subject_tracker
        resolved_tracker_pref = self._resolve_single_subject_tracker_preference(single_video_config)
        if resolved_tracker_pref is None:
            resolved_tracker_pref = previous_tracker_pref

        if resolved_mode is not None and resolved_mode != previous_mode:
            self.settings.video_processing.single_animal_per_aquarium = resolved_mode
            log.info(
                "controller.processing.single_animal_mode",
                enabled=resolved_mode,
                previous=previous_mode,
                scope="single_video" if single_video_config else "project",
            )

        tracker_changed = resolved_tracker_pref != previous_tracker_pref
        if tracker_changed:
            self.settings.tracking.use_single_subject_tracker = resolved_tracker_pref
            log.info(
                "controller.processing.single_subject_tracker",
                enabled=resolved_tracker_pref,
                previous=previous_tracker_pref,
                scope="single_video" if single_video_config else "project",
            )

        self._configure_single_subject_tracker(self.settings.tracking.use_single_subject_tracker)
        self._publish_processing_mode(
            source="processing.temporary_mode.enter",
            force=True,
        )

        try:
            yield self.settings.video_processing.single_animal_per_aquarium
        finally:
            if self.settings.video_processing.single_animal_per_aquarium != previous_mode:
                self.settings.video_processing.single_animal_per_aquarium = previous_mode
                log.info(
                    "controller.processing.single_animal_mode_restored",
                    restored=previous_mode,
                )

            if tracker_changed:
                self.settings.tracking.use_single_subject_tracker = previous_tracker_pref
                log.info(
                    "controller.processing.single_subject_tracker_restored",
                    restored=previous_tracker_pref,
                )

            self._configure_single_subject_tracker(
                self.settings.tracking.use_single_subject_tracker
            )
            self._publish_processing_mode(
                source="processing.temporary_mode.exit",
                force=True,
            )
