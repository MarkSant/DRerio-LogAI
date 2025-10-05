"""
Wizard Adapter - Translates wizard output to controller format.

This module provides a bridge between the new 5-step wizard and the existing
controller interface, ensuring backward compatibility.
"""

from pathlib import Path
from typing import Optional

import structlog

from zebtrack.ui.wizard.enums import ProjectType

log = structlog.get_logger()


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
    required_fields = ["project_path", "project_name", "video_paths", "project_type"]
    missing = [f for f in required_fields if f not in wizard_data]
    if missing:
        raise ValueError(f"Missing required wizard fields: {missing}")

    # Extract video paths (wizard may have scanned from folders)
    video_paths = wizard_data.get("video_paths", [])
    if not video_paths:
        raise ValueError("No video paths found in wizard data")

    # Determine project type
    project_type_value = wizard_data.get("project_type", ProjectType.EXPERIMENTAL.value)
    is_exploratory = project_type_value == ProjectType.EXPLORATORY.value

    # Map to controller format (always "pre-recorded" for wizard v1.5)
    # Future: wizard will support live projects in v2.0
    controller_data = {
        "project_path": wizard_data["project_path"],
        "project_type": "pre-recorded",  # Wizard v1.5 only supports pre-recorded
        "video_files": video_paths,
        # Calibration defaults (wizard v1.5 doesn't collect these, use defaults)
        "num_aquariums": 1,
        "animals_per_aquarium": 1,
        "aquarium_width_cm": 10.0,
        "aquarium_height_cm": 10.0,
        # Processing intervals (use defaults for now)
        "analysis_interval_frames": 10,
        "display_interval_frames": 10,
        # Detection methods (use defaults from settings)
        "aquarium_method": "seg",
        "animal_method": "det",
        # Live recording (not supported in wizard v1.5)
        "use_timed_recording": False,
        "recording_duration_s": 0,
        "use_countdown": False,
        "countdown_duration_s": 0,
        # Experimental design (only for experimental projects)
        "experiment_days": None,
        "subjects_per_group": None,
        "num_groups": None,
        "group_names": None,
    }

    # Add experimental design if detected
    if not is_exploratory:
        detected_design = wizard_data.get("detected_design")
        if detected_design:
            groups = detected_design.get("groups", [])
            days = detected_design.get("days", [])
            subjects = detected_design.get("subjects_per_group")

            if groups:
                controller_data["num_groups"] = len(groups)
                controller_data["group_names"] = groups

            if days:
                controller_data["experiment_days"] = len(days)

            if subjects:
                controller_data["subjects_per_group"] = subjects

    # Store wizard metadata for future use (parquet import, etc.)
    controller_data["_wizard_metadata"] = {
        "wizard_schema_version": wizard_data.get("wizard_schema_version"),
        "created_at": wizard_data.get("created_at"),
        "has_folder_structure": wizard_data.get("has_folder_structure"),
        "folder_meaning": wizard_data.get("folder_meaning"),
        "has_parquets": wizard_data.get("has_parquets"),
        "parquet_import_scope": wizard_data.get("parquet_import_scope"),
        "detected_design": wizard_data.get("detected_design"),
        "scanned_videos": wizard_data.get("scanned_videos"),
        "import_config": wizard_data.get("import_config"),
        "roi_merge_strategy": wizard_data.get("roi_merge_strategy"),
        "parquet_summary": wizard_data.get("parquet_summary"),
        "video_count": wizard_data.get("video_count"),
    }

    log.info(
        "wizard.adapter.success",
        project_path=controller_data["project_path"],
        video_count=len(video_paths),
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
