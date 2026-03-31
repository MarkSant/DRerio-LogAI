"""Mixin: single video processing (9-step flow) and helpers.

Extracted from VideoProcessingCoordinator (Etapa 2b).
Handles the complete lifecycle of processing a single video:
- 9-step orchestration flow
- Calibration/metadata extraction
- Registration and zone persistence
- Detector setup and execution
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.core.detection import MultiAquariumZoneData, ZoneData
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.core.video.processing_mode import ProcessingMode
from zebtrack.core.video.processing_worker import (
    ProcessingWorker,
)
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import UIEvents

if TYPE_CHECKING:
    from threading import Event

    from zebtrack.coordinators.multi_aquarium_coordinator import MultiAquariumCoordinator
    from zebtrack.coordinators.sequential_processing_coordinator import (
        SequentialProcessingCoordinator,
    )
    from zebtrack.settings import Settings

log = structlog.get_logger()


class SingleVideoMixin:
    """Mixin for single video processing workflows.

    Requires host class to provide:
    - self.project_manager
    - self.detector_service / self.detector
    - self.settings
    - self.view
    - self.cancel_event
    - self.processing_worker / self.processing_thread
    - self._multi_aquarium_coordinator
    - self._sequential_coordinator
    - self._publish_event(event, payload)
    - self.validate_can_start_processing(...)
    - self._show_validation_error(...)
    - self._get_video_dimensions(...)
    - self.create_processing_callbacks(...)
    - self.create_processing_context(...)
    """

    # Declare host-provided attributes for mypy (set by coordinator __init__)
    project_manager: ProjectManager
    settings: Settings
    view: Any
    detector: Any
    cancel_event: Event
    processing_worker: ProcessingWorker | None
    processing_thread: Any
    _multi_aquarium_coordinator: MultiAquariumCoordinator | None
    _sequential_coordinator: SequentialProcessingCoordinator | None

    # Host-provided methods (declared for mypy, implemented by host/other mixins)
    _publish_event: Any
    validate_can_start_processing: Any
    _show_validation_error: Any
    _get_video_dimensions: Any
    create_processing_callbacks: Any
    create_processing_context: Any

    def start_single_video_processing(
        self,
        video_path: Path | str,
        config: dict,
        zone_data: ZoneData | MultiAquariumZoneData,
    ) -> None:
        """Start the actual processing for a single video after zone setup."""
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        log.info("workflow.single_video.processing_start", video=str(video_path))

        # 1. Sequential mode check
        is_multi_aq = hasattr(zone_data, "aquariums")
        if is_multi_aq:
            fresh_zone_data = self.project_manager.get_multi_aquarium_zone_data(video_path)
            if fresh_zone_data:
                zone_data = fresh_zone_data
            if isinstance(zone_data, MultiAquariumZoneData):
                for aq in zone_data.aquariums:
                    if not aq.subject_id:
                        log.warning(
                            "processing.missing_subject_id",
                            aquarium_id=aq.id,
                            video=str(video_path),
                        )
                        self._publish_event(
                            UIEvents.UI_SHOW_ERROR,
                            payloads.MessagePayload(
                                title="Configuração Incompleta",
                                message=(
                                    f"Aquário {aq.id} não tem sujeito definido. "
                                    "Configure os aquários antes de processar."
                                ),
                            ),
                        )
                        return

        use_seq = is_multi_aq and getattr(zone_data, "sequential_processing", False)

        # 2. Calibration
        calib_data = self._extract_calibration_from_config(config)
        n_aq = calib_data["n"]

        if use_seq:
            seq = self._sequential_coordinator
            if seq:
                seq._handle_sequential_single_video_start(str(video_path), zone_data, config)
            return

        # 3. Validate
        val = self.validate_can_start_processing(
            check_project_loaded=False, check_zones=False, check_videos_exist=False
        )
        if not val.is_valid:
            self._show_validation_error(val)
            return

        self.project_manager.set_active_zone_video(video_path)

        # 4. Multi-aq UI sync
        zone_data = self._sync_multi_aquarium_setup(video_path, n_aq, zone_data)

        # 5. Persist calibration
        self._persist_single_video_calibration(config, calib_data)

        # 6. Register video
        self._ensure_single_video_registered(video_path, config, zone_data, calib_data)

        # 7. Save zones
        self._ensure_single_video_zones_saved(video_path, zone_data)

        # 8. Setup detector
        if not self._setup_detector_for_single_video(video_path, zone_data):
            return

        mac = self._multi_aquarium_coordinator
        single_video_config = config if isinstance(config, dict) else None
        resolved_tracker_pref = (
            mac._resolve_single_subject_tracker_preference(single_video_config) if mac else None
        )
        if (
            resolved_tracker_pref is not None
            and resolved_tracker_pref != self.settings.tracking.use_single_subject_tracker
        ):
            self.settings.tracking.use_single_subject_tracker = resolved_tracker_pref
            self.settings.video_processing.single_animal_per_aquarium = resolved_tracker_pref

        if mac:
            mac._configure_single_subject_tracker(self.settings.tracking.use_single_subject_tracker)
            effective_mode = (
                ProcessingMode.SINGLE_SUBJECT
                if self.settings.tracking.use_single_subject_tracker
                else ProcessingMode.MULTI_TRACK
            )
            mac._active_processing_mode = effective_mode
            mac._publish_processing_mode(source="single_video.preflight", force=True)

        # 9. Execute
        self._execute_single_video_analysis(video_path)

    def _extract_calibration_from_config(self, config: dict) -> dict:
        """Extract calibration params from config."""
        n_aq, w_cm, h_cm = 1, None, None
        if isinstance(config, dict):
            try:
                n_aq = int(config.get("num_aquariums", 1))
                self.settings.analysis_config.num_aquariums = n_aq
            except (TypeError, ValueError):
                log.debug("config.num_aquariums.parse_skipped", exc_info=True)
            try:
                raw_w = config.get("aquarium_width_cm")
                if raw_w is not None and str(raw_w).strip():
                    w_cm = float(raw_w)
            except (TypeError, ValueError):
                log.debug("config.aquarium_width.parse_skipped", exc_info=True)
            try:
                raw_h = config.get("aquarium_height_cm")
                if raw_h is not None and str(raw_h).strip():
                    h_cm = float(raw_h)
            except (TypeError, ValueError):
                log.debug("config.aquarium_height.parse_skipped", exc_info=True)
        return {"w": w_cm, "h": h_cm, "n": n_aq}

    def _extract_metadata_from_config(self, config: dict) -> dict:
        """Extract metadata from single video config."""
        metadata: dict[str, Any] = {}
        if config:
            for key in ["group", "group_display_name", "day", "subject"]:
                if key in config:
                    metadata[key] = config[key]
            for dim_key in ("aquarium_width_cm", "aquarium_height_cm"):
                if dim_key in config:
                    val = config.get(dim_key)
                    if val not in (None, ""):
                        try:
                            metadata[dim_key] = float(str(val))
                        except (TypeError, ValueError):
                            log.debug(
                                "config.metadata_dim.parse_skipped", key=dim_key, exc_info=True
                            )
        metadata.setdefault("group", "single_video")
        metadata.setdefault("group_display_name", "Vídeo Único")
        metadata.setdefault("day", "1")
        metadata.setdefault("subject", "1")
        return metadata

    def _save_multi_aquarium_config_to_calibration(self, calibration_dict: dict) -> None:
        """Convert custom_regex_patterns from wizard to MultiAquariumData format."""
        wizard_metadata = (
            self.project_manager.project_data.get("_wizard_metadata", {})
            if self.project_manager.project_data
            else {}
        )
        if not wizard_metadata:
            return
        custom_patterns = wizard_metadata.get("custom_regex_patterns")
        if not custom_patterns or not isinstance(custom_patterns, dict):
            return
        from zebtrack.ui.wizard.models import MultiAquariumData

        try:
            combined_pattern = MultiAquariumData.build_combined_regex_pattern(
                group_pattern=custom_patterns.get("group_pattern"),
                day_pattern=custom_patterns.get("day_pattern"),
                subject_pattern=custom_patterns.get("subject_pattern"),
            )
            if combined_pattern:
                calibration_dict["multi_aquarium"] = {
                    "enabled": False,
                    "regex_pattern": combined_pattern,
                    "regex_group_field": "group",
                    "regex_subject_field": "subject",
                    "regex_day_field": "day",
                    "aquarium_configs": [],
                }
        except (ValueError, KeyError, TypeError) as e:
            log.error("calibration.multi_aquarium.conversion_failed", error=str(e))

    def _sync_multi_aquarium_setup(self, video_path: Path | str, n_aq, zone_data) -> Any:
        """Sync multi-aquarium setup with UI and model."""
        if n_aq > 1:
            from zebtrack.core.detection import AquariumData

            curr = self.project_manager.get_multi_aquarium_zone_data(video_path)
            if not curr:
                aqs = [AquariumData(id=i) for i in range(n_aq)]
                new_m = MultiAquariumZoneData(aquariums=aqs)
                persist = bool(self.project_manager.project_path)
                self.project_manager.save_multi_aquarium_zone_data(
                    video_path,
                    new_m,
                    persist=persist,
                )
                zone_data = new_m
            if self.view and hasattr(self.view, "zone_controls"):
                self.view.zone_controls.update_aquarium_count(n_aq)
                self.view.zone_controls.set_active_aquarium(0)
        elif self.view and hasattr(self.view, "zone_controls"):
            self.view.zone_controls.update_aquarium_count(1)
        return zone_data

    def _persist_single_video_calibration(self, config, calib) -> None:
        """Persist calibration and settings for single video."""
        w_cm, h_cm = calib["w"], calib["h"]
        if not (w_cm and h_cm):
            return
        c = self.project_manager.project_data.get("calibration") or {}
        c.setdefault("num_aquariums", c.get("num_aquariums", 1))
        c.setdefault("animals_per_aquarium", c.get("animals_per_aquarium", 1))
        c.update({"aquarium_width_cm": w_cm, "aquarium_height_cm": h_cm})
        self._save_multi_aquarium_config_to_calibration(c)
        self.project_manager.project_data["calibration"] = c

        mac = self._multi_aquarium_coordinator
        a_int, d_int = mac._determine_processing_intervals(config) if mac else (10, 10)
        self.project_manager.project_data["analysis_interval_frames"] = a_int
        self.project_manager.project_data["display_interval_frames"] = d_int

        if "behavioral_analysis" in config:
            self.project_manager.project_data["behavioral_config"] = config["behavioral_analysis"]

        if self.project_manager.project_path:
            self.project_manager.save_project()
        log.info("workflow.single_video.cal_saved", w=w_cm, h=h_cm)

    def _ensure_single_video_registered(
        self, video_path: Path | str, config, zone_data, calib
    ) -> None:
        """Ensure single video is registered in project."""
        v_entry = self.project_manager.find_video_entry(path=video_path)
        if v_entry:
            return
        w_cm, h_cm = calib["w"], calib["h"]
        meta = self._extract_metadata_from_config(config)
        if w_cm:
            meta.setdefault("aquarium_width_cm", w_cm)
        if h_cm:
            meta.setdefault("aquarium_height_cm", h_cm)

        has_a, has_r = False, False
        if zone_data:
            if hasattr(zone_data, "aquariums"):
                has_a = bool(zone_data.aquariums)
                has_r = any(bool(aq.roi_polygons) for aq in zone_data.aquariums)
            else:
                has_a = bool(zone_data.polygon)
                has_r = bool(zone_data.roi_polygons)

        v_dict: dict[str, Any] = {
            "path": Path(video_path).as_posix(),
            "experiment_id": os.path.splitext(os.path.basename(str(video_path)))[0],
            "status": "processing",
            "has_arena": has_a,
            "has_rois": has_r,
        }
        if meta:
            v_dict["metadata"] = meta
        self.project_manager.add_video_batch([v_dict], save_project=False)
        self._publish_event(
            UIEvents.UI_REFRESH_PROJECT_VIEWS,
            payloads.ProjectViewsRefreshRequestedPayload(reason="reg", imm=True),
        )

    def _ensure_single_video_zones_saved(self, video_path: Path | str, zone_data) -> None:
        """Ensure zones are saved for single video."""
        should_s = False
        if zone_data:
            if hasattr(zone_data, "aquariums"):
                should_s = bool(zone_data.aquariums)
            else:
                should_s = bool(zone_data.polygon or zone_data.roi_polygons)
        if should_s:
            self.project_manager.save_zone_data(
                zone_data, video_path, persist=bool(self.project_manager.project_path)
            )

    def _setup_detector_for_single_video(self, video_path: Path | str, zone_data) -> bool:
        """Setup detector with zones for single video."""
        if not self.detector:
            return True
        dims = self._get_video_dimensions(str(video_path))
        if dims is None:
            self._publish_event(
                UIEvents.UI_SHOW_ERROR,
                payloads.MessagePayload(
                    title="Erro",
                    message=f"Não foi possível abrir: {video_path}",
                ),
            )
            return False
        w, h = dims
        self.detector.set_zones(zone_data, w, h)
        has_aq = bool(zone_data and (zone_data.polygon or hasattr(zone_data, "aquariums")))
        self.detector.set_aquarium_region_defined(has_aq)
        return True

    def _execute_single_video_analysis(self, video_path: Path | str) -> None:
        """Final execution start for single video."""
        scanned = ProjectManager.scan_input_paths([str(video_path)])
        if not scanned:
            if self.view:
                self.view.dialog_manager.show_error(
                    "Erro", "Não foi possível identificar vídeo válido."
                )
            return
        video_stem = Path(video_path).stem
        out_dir = self.project_manager.resolve_results_directory(
            video_stem, video_path=str(video_path)
        )
        self.process_videos(scanned, out_dir)

    def process_videos(self, videos_to_process: list[dict], output_base_dir: Path | str) -> None:
        """Execute processing for a list of videos (legacy support)."""
        output_dir_str = str(output_base_dir)

        # Reuse the unified callback factory
        callbacks = self.create_processing_callbacks(videos_to_process)
        context = self.create_processing_context(videos_to_process, output_dir_str)
        if self.cancel_event:
            self.cancel_event.clear()
        self.processing_worker = ProcessingWorker(context, callbacks)
        self.processing_thread = self.processing_worker.start_in_thread()
