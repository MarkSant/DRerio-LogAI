"""
Wizard Adapter - Translates wizard output to controller format.

This module provides a bridge between the new 5-step wizard and the existing
controller interface, ensuring backward compatibility.
"""

from __future__ import annotations

import copy
import re
from typing import Optional

import structlog

from zebtrack.settings import settings
from zebtrack.ui.wizard.enums import ProjectType

log = structlog.get_logger()


def _normalise_subject_id(raw_subject: str) -> str:
    """Normalize subject identifiers to the ``SXX`` format when possible."""

    if raw_subject is None:
        return raw_subject

    value = raw_subject.strip()
    if not value:
        return raw_subject

    # Remove common prefixes for digits-only normalization
    # Examples: "Subject01", "S01", "s1" → "S01"
    match = re.match(r"(?i)(?:subject|subj|s)?\s*([0-9]{1,3})", value)
    if match:
        return f"S{int(match.group(1)):02d}"

    return raw_subject


def _normalise_day_label(day_value) -> str | None:
    if day_value in (None, ""):
        return None
    if isinstance(day_value, (int, float)) and not isinstance(day_value, bool):
        try:
            return f"{int(day_value):02d}"
        except (TypeError, ValueError):
            return str(day_value)

    value_str = str(day_value).strip()
    if not value_str:
        return None

    lower_value = value_str.lower()
    if lower_value == "sem dia":
        return "Sem Dia"

    match = re.search(r"(\d+)", value_str)
    if match:
        try:
            return f"{int(match.group(1)):02d}"
        except ValueError:
            return value_str

    return value_str


def enrich_videos_with_design_metadata(
    scanned_videos: list[dict],
    detected_design: dict | None,
    custom_patterns: dict | None = None,
    group_display_names: dict[str, str] | None = None,
) -> list[dict]:
    """Enrich scanned videos with experimental metadata derived from the design.

    Args:
        scanned_videos: Video descriptors produced by ``scan_input_paths``.
        detected_design: Detected experimental design information.
        custom_patterns: Optional regex patterns configured by the user.
        group_display_names: Optional mapping from group IDs to friendly names.

    Returns:
        A **new** list of video descriptors with metadata persisted both at the
        root level (``group``, ``day`` ...) and inside a dedicated ``metadata``
        dictionary suitable for persistence in ``project.json``.
    """

    if not scanned_videos:
        return []

    if not detected_design:
        return [copy.deepcopy(video) for video in scanned_videos]

    group_display_names = group_display_names or {}
    custom_patterns = custom_patterns or {}

    groups = detected_design.get("groups") or []
    days = detected_design.get("days") or []
    subjects_per_group = detected_design.get("subjects_per_group") or {}

    group_lookup = {str(g).lower(): g for g in groups if isinstance(g, str)}
    day_lookup = {str(d).lower(): d for d in days if isinstance(d, str)}
    for canonical_day in list(day_lookup.values()):
        if isinstance(canonical_day, str):
            digit_match = re.search(r"(\d+)", canonical_day)
            if digit_match:
                day_lookup[digit_match.group(1)] = canonical_day

    subject_lookup = {}
    for group_id, subjects in subjects_per_group.items():
        if not isinstance(subjects, (list, tuple, set)):
            continue
        subject_lookup[group_id] = {
            str(subject).lower(): subject for subject in subjects if subject is not None
        }

    def _build_pattern(explicit: str | None, values: list[str]) -> str | None:
        if explicit:
            return explicit

        valid_values = [v for v in values if isinstance(v, str) and v]
        if not valid_values:
            return None

        escaped = [re.escape(v) for v in valid_values]
        return f"({'|'.join(escaped)})"

    group_pattern = _build_pattern(custom_patterns.get("group_pattern"), groups)

    day_pattern = _build_pattern(custom_patterns.get("day_pattern"), days)

    # Build subject pattern from all subjects when explicit pattern is absent.
    all_subject_values = [
        subject
        for values in subject_lookup.values()
        for subject in values.values()
        if subject is not None
    ]
    subject_pattern = _build_pattern(
        custom_patterns.get("subject_pattern"), all_subject_values
    )

    enriched_videos: list[dict] = []

    for original_video in scanned_videos:
        enriched = copy.deepcopy(original_video)
        path_str = str(enriched.get("path", ""))

        metadata: dict = copy.deepcopy(enriched.get("metadata") or {})

        # --- Group extraction -------------------------------------------------
        group_id = metadata.get("group") or enriched.get("group")
        if not group_id and group_pattern:
            match = re.search(group_pattern, path_str, re.IGNORECASE)
            if match:
                matched_group = match.group(1) if match.groups() else match.group(0)
                lookup_key = matched_group.lower()
                group_id = group_lookup.get(lookup_key, matched_group)

        if isinstance(group_id, str):
            metadata["group"] = group_id
            enriched["group"] = group_id
            display_name = group_display_names.get(group_id) or group_lookup.get(
                group_id.lower(), group_id
            )
            metadata.setdefault("group_display_name", display_name)
            enriched["group_display_name"] = metadata.get("group_display_name")

        # --- Day extraction ---------------------------------------------------
        day_value = metadata.get("day") or enriched.get("day")
        if not day_value and day_pattern:
            match = re.search(day_pattern, path_str, re.IGNORECASE)
            if match:
                matched_day = match.group(1) if match.groups() else match.group(0)
                if isinstance(matched_day, str) and matched_day.isdigit():
                    matched_day = f"Day{int(matched_day):02d}"
                lookup_key = matched_day.lower()
                day_value = day_lookup.get(lookup_key, matched_day)

        if day_value is not None:
            metadata["day"] = day_value
            enriched["day"] = day_value
            day_label = _normalise_day_label(day_value)
            if day_label:
                metadata.setdefault("day_label", day_label)
                enriched["day_label"] = day_label

        # --- Subject extraction -----------------------------------------------
        subject_value = metadata.get("subject") or enriched.get("subject")
        if not subject_value and subject_pattern:
            match = re.search(subject_pattern, path_str, re.IGNORECASE)
            if match:
                matched_subject = match.group(1) if match.groups() else match.group(0)
                normalised = _normalise_subject_id(matched_subject)
                subject_value = normalised

        if subject_value is None and group_id:
            candidates = subject_lookup.get(group_id, {})
            for candidate_lower, candidate_value in candidates.items():
                if candidate_lower in path_str.lower():
                    subject_value = candidate_value
                    break

        if subject_value is not None:
            metadata["subject"] = subject_value
            enriched["subject"] = subject_value

        if metadata:
            enriched["metadata"] = metadata

        enriched_videos.append(enriched)

    log.info(
        "wizard.videos_enriched",
        total=len(enriched_videos),
        with_group=sum(1 for v in enriched_videos if v.get("group")),
        with_day=sum(1 for v in enriched_videos if v.get("day")),
        with_subject=sum(1 for v in enriched_videos if v.get("subject")),
    )

    return enriched_videos


def adapt_wizard_data_to_controller_format(wizard_data: dict) -> dict:
    """
    Transform wizard output to CreateProjectDialog format expected by controller.

    The wizard produces a rich data structure with design detection and import
    configuration. This adapter translates it to the format expected by
    controller.create_project_workflow().

    Args:
        wizard_data: Output from WizardDialog.result

    Returns:
        dict: Data in CreateProjectDialog format with keys:
            - project_path: Full path to project directory
            - project_type: "pre-recorded" or "live"
            - video_files: List of video paths
            - num_aquariums: int
            - animals_per_aquarium: int
            - aquarium_width_cm: float
            - aquarium_height_cm: float
            - analysis_interval_frames: int
            - display_interval_frames: int
            - aquarium_method: "seg" or "det"
            - animal_method: "seg" or "det"
            - use_timed_recording: bool
            - recording_duration_s: float
            - use_countdown: bool
            - countdown_duration_s: int
            - experiment_days: int or None
            - subjects_per_group: int or None
            - num_groups: int or None
            - group_names: list[str] or None
            - _wizard_metadata: dict (additional metadata from wizard)

    Raises:
        ValueError: If required wizard fields are missing
    """
    log.info("wizard.adapter.start", wizard_data_keys=list(wizard_data.keys()))

    # Validate required fields
    required_fields = ["project_path", "project_name", "project_type"]
    missing = [f for f in required_fields if f not in wizard_data]
    if missing:
        raise ValueError(f"Missing required wizard fields: {missing}")

    # Determine project type
    project_type_value = wizard_data.get("project_type", ProjectType.EXPERIMENTAL.value)
    is_live = project_type_value == ProjectType.LIVE.value
    is_exploratory = project_type_value == ProjectType.EXPLORATORY.value

    # Base controller data (common to all project types)
    controller_data = {
        "project_path": wizard_data["project_path"],
        "project_type": "live" if is_live else "pre-recorded",
        # Calibration data (collected in v2.0, use defaults as fallback)
        "num_aquariums": wizard_data.get("num_aquariums", 1),
        "animals_per_aquarium": wizard_data.get("animals_per_aquarium", 1),
        "aquarium_width_cm": wizard_data.get("aquarium_width_cm", 10.0),
        "aquarium_height_cm": wizard_data.get("aquarium_height_cm", 10.0),
        # Processing intervals (use defaults for now)
        "analysis_interval_frames": 10,
        "display_interval_frames": 10,
        # Detection methods (use defaults from settings)
        "aquarium_method": "seg",
        "animal_method": "det",
        "use_single_subject_tracker": False,
        # Experimental design (initialized to None, populated later if applicable)
        "experiment_days": None,
        "subjects_per_group": None,
        "num_groups": None,
        "group_names": None,
    }

    animals_per_aquarium = controller_data["animals_per_aquarium"]
    controller_data["use_single_subject_tracker"] = animals_per_aquarium == 1

    if "use_openvino" in wizard_data:
        controller_data["use_openvino"] = bool(wizard_data.get("use_openvino"))
    else:
        use_openvino_default = False
        try:
            use_openvino_default = bool(settings.model_selection.use_openvino)
        except AttributeError:
            use_openvino_default = False
        controller_data["use_openvino"] = use_openvino_default

    video_files: list[dict] = []

    detected_design = wizard_data.get("detected_design")
    custom_patterns = wizard_data.get("custom_regex_patterns")
    enriched_scanned_videos = copy.deepcopy(wizard_data.get("scanned_videos", []))

    if is_live:
        # Live project: Use live configuration data
        controller_data.update({
            "camera_index": wizard_data.get("camera_index", 0),
            "use_arduino": wizard_data.get("use_arduino", False),
            "arduino_port": wizard_data.get("arduino_port", ""),
            "use_timed_recording": wizard_data.get("use_timed_recording", False),
            "recording_duration_s": wizard_data.get("recording_duration_s", 0),
            "use_countdown": wizard_data.get("use_countdown", False),
            "countdown_duration_s": wizard_data.get("countdown_duration_s", 0),
            "video_files": [],  # Live projects don't have pre-recorded files
        })
    else:
        # Pre-recorded project: Use scanned videos
        scanned_videos = enriched_scanned_videos
        if not scanned_videos:
            raise ValueError("No scanned videos found in wizard data")

        group_display_names = None
        if detected_design:
            group_display_names = detected_design.get("group_display_names")
            scanned_videos = enrich_videos_with_design_metadata(
                scanned_videos,
                detected_design,
                custom_patterns,
                group_display_names,
            )
            enriched_scanned_videos = copy.deepcopy(scanned_videos)

        # Convert scanned videos to format expected by add_video_batch
        # Each video needs: {"path": str, "has_data": bool}
        for video_info in scanned_videos:
            converted = copy.deepcopy(video_info)
            converted["has_data"] = bool(
                video_info.get("has_data", video_info.get("has_complete_data", False))
            )
            video_files.append(converted)

        controller_data.update({
            "video_files": video_files,
            "use_timed_recording": False,
            "recording_duration_s": 0,
            "use_countdown": False,
            "countdown_duration_s": 0,
        })

    # Add experimental design if detected

    if not is_exploratory:
        if detected_design:
            groups = detected_design.get("groups", [])
            days = detected_design.get("days", [])
            subjects_dict = detected_design.get("subjects_per_group", {})

            if groups:
                controller_data["num_groups"] = len(groups)
                controller_data["group_names"] = groups

            if days:
                controller_data["experiment_days"] = len(days)

            # Calculate subjects_per_group from detected subjects dict
            # subjects_dict is {"Control": ["S01", "S02"], ...}
            # Extract the max number of subjects across groups
            if subjects_dict and isinstance(subjects_dict, dict):
                subject_counts = [
                    len(subjects) for subjects in subjects_dict.values() if subjects
                ]
                if subject_counts:
                    controller_data["subjects_per_group"] = max(subject_counts)

    # Store wizard metadata for future use (parquet import, etc.)
    wizard_scanned_videos = (
        enriched_scanned_videos if not is_live else wizard_data.get("scanned_videos")
    )

    controller_data["_wizard_metadata"] = {
        "wizard_schema_version": wizard_data.get("wizard_schema_version"),
        "created_at": wizard_data.get("created_at"),
        "has_folder_structure": wizard_data.get("has_folder_structure"),
        "folder_meaning": wizard_data.get("folder_meaning"),
        "has_parquets": wizard_data.get("has_parquets"),
        "parquet_import_scope": wizard_data.get("parquet_import_scope"),
        "detected_design": wizard_data.get("detected_design"),
        "scanned_videos": wizard_scanned_videos,
        "import_config": wizard_data.get("import_config"),
        "roi_merge_strategy": wizard_data.get("roi_merge_strategy"),
        "parquet_summary": wizard_data.get("parquet_summary"),
        "video_count": wizard_data.get("video_count"),
        "folder_preview": wizard_data.get("folder_preview"),
        "use_openvino": controller_data.get("use_openvino"),
    }

    log.info(
        "wizard.adapter.success",
        project_path=controller_data["project_path"],
        video_count=len(video_files),
        has_design=detected_design is not None if not is_exploratory else None,
    )

    return controller_data


def extract_parquet_import_plan(wizard_data: dict) -> Optional[dict]:
    """
    Extract parquet import plan from wizard metadata.

    This can be used by the controller to import zones and trajectories
    from existing parquet files.

    Args:
        wizard_data: Output from WizardDialog.result

    Returns:
        dict with keys:
            - import_config: List of per-video import configurations
            - roi_merge_strategy: How to handle ROI conflicts
            - parquet_summary: Summary of available parquets
        or None if no parquets to import
    """
    if not wizard_data.get("has_parquets"):
        return None

    import_config = wizard_data.get("import_config", [])
    if not import_config:
        return None

    return {
        "import_config": import_config,
        "roi_merge_strategy": wizard_data.get("roi_merge_strategy", "replace"),
        "parquet_summary": wizard_data.get("parquet_summary", {}),
    }
