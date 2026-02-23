import os
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
import structlog

from zebtrack.core.project.project_manager import ProjectManager


@pytest.fixture
def project_manager(tmp_path):
    settings = SimpleNamespace(tracking=SimpleNamespace(use_single_subject_tracker=True))
    pm = ProjectManager(settings_obj=settings)
    project_path = tmp_path / "project"
    project_path.mkdir(parents=True, exist_ok=True)
    pm.project_path = project_path
    pm.project_data = {"batches": [], "zones_by_video": {}, "detection_zones": {}, "tracking": {}}
    return pm


def test_validate_project_parameters_bounds(project_manager):
    with pytest.raises(ValueError):
        project_manager._validate_project_parameters(
            num_aquariums=0,
            animals_per_aquarium=1,
            aquarium_width_cm=1.0,
            aquarium_height_cm=1.0,
            analysis_interval_frames=10,
            display_interval_frames=10,
            camera_index=0,
            project_type="Pre-recorded",
            video_files=None,
        )

    project_manager._validate_project_parameters(
        num_aquariums=1,
        animals_per_aquarium=1,
        aquarium_width_cm=0.0,
        aquarium_height_cm=0.0,
        analysis_interval_frames=10,
        display_interval_frames=10,
        camera_index=0,
        project_type="Pre-recorded",
        video_files=None,
    )


def test_apply_project_migrations_sets_tracking_default(project_manager):
    loaded = {
        "calibration": {},
        "analysis_profiles": [],
        "tracking": {"use_single_subject_tracker": None},
    }
    migrated_data, migrated, fields = project_manager._apply_project_migrations(
        loaded,
        structlog.get_logger().bind(test="migrations"),
    )

    assert migrated is True
    assert "tracking.use_single_subject_tracker" in fields
    assert migrated_data["tracking"]["use_single_subject_tracker"] is True
    assert migrated_data["analysis_profiles"]


def test_load_zones_from_parquet_roundtrip(tmp_path):
    arena_path = tmp_path / "arena.parquet"
    rois_path = tmp_path / "rois.parquet"

    pd.DataFrame({"x": [0, 1, 1, 0], "y": [0, 0, 1, 1]}).to_parquet(arena_path)
    pd.DataFrame(
        {
            "roi_name": ["R1", "R1", "R2", "R2"],
            "point_index": [0, 1, 0, 1],
            "x": [10, 20, 30, 40],
            "y": [10, 20, 30, 40],
        }
    ).to_parquet(rois_path)

    video_info = {
        "path": "video.mp4",
        "parquet_files": {"arena": str(arena_path), "rois": str(rois_path)},
    }

    zone_data = ProjectManager.load_zones_from_parquet(video_info)

    assert zone_data is not None
    assert len(zone_data.polygon) == 4
    assert zone_data.roi_names == ["R1", "R2"]
    assert len(zone_data.roi_colors) == len(zone_data.roi_names)


@patch.object(ProjectManager, "scan_input_paths")
def test_copy_zone_parquet_files_updates_project_entry(scan_input_paths, project_manager, tmp_path):
    arena_src = tmp_path / "src_arena.parquet"
    rois_src = tmp_path / "src_rois.parquet"
    pd.DataFrame({"x": [0, 1], "y": [0, 1]}).to_parquet(arena_src)
    pd.DataFrame({"roi_name": ["R1"], "point_index": [0], "x": [1], "y": [1]}).to_parquet(rois_src)

    scan_input_paths.return_value = [
        {"path": "src.mp4", "parquet_files": {"arena": str(arena_src), "rois": str(rois_src)}},
    ]

    target_video_path = tmp_path / "videos" / "target.mp4"
    video_entry = {
        "path": str(target_video_path),
        "metadata": {"group": "G1", "day": 2, "subject": "A"},
    }
    project_manager.project_data["batches"].append({"videos": [video_entry]})

    copied = project_manager.copy_zone_parquet_files("src.mp4", str(target_video_path))

    assert copied
    parquet_map = video_entry.get("parquet_files")
    assert isinstance(parquet_map, dict)
    assert os.path.exists(parquet_map["arena"])
    assert os.path.exists(parquet_map["rois"])

    hierarchical_dir = project_manager.resolve_results_directory(
        "target", video_path=str(target_video_path)
    )
    assert (hierarchical_dir / "1_ProcessingArea_target.parquet").exists()
    assert (hierarchical_dir / "2_AreasOfInterest_target.parquet").exists()
