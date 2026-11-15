"""Extended unit tests for ProjectManager in core/project/project_manager.py."""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import structlog

from zebtrack.core.detection import AquariumData, MultiAquariumZoneData, ZoneData
from zebtrack.core.project.project_manager import (
    CONFIG_FILE_NAME,
    ProjectInvalidError,
    ProjectManager,
    _threadsafe,
)
from zebtrack.core.project.zone_manager import ZoneManager
from zebtrack.core.state_manager import StateManager
from zebtrack.settings import load_settings


class TestProjectManager(unittest.TestCase):
    def setUp(self):
        """Set up a temporary directory for testing."""
        self.test_dir = tempfile.mkdtemp(prefix="test_project_manager_")
        # Load settings for tests
        self.settings_obj = load_settings()

    def tearDown(self):
        """Clean up the temporary directory after tests."""
        if os.path.exists(self.test_dir):
            self._cleanup_test_directory(Path(self.test_dir))
        ProjectManager.clear_scan_cache()

    @staticmethod
    def _cleanup_test_directory(path: Path, retries: int = 5, delay: float = 0.15) -> None:
        """Attempt to delete the directory even if Windows keeps file handles open."""

        def _handle_remove_error(func, target, exc_info):
            try:
                os.chmod(target, stat.S_IWRITE)
                func(target)
            except Exception:
                # Ignore so the retry loop can continue
                pass

        last_error: OSError | None = None
        for attempt in range(retries):
            try:
                shutil.rmtree(path, onerror=_handle_remove_error)
                return
            except OSError as exc:  # pragma: no cover - defensive for Windows timing quirks
                last_error = exc
                time.sleep(delay * (attempt + 1))  # intentional retry backoff delay

        if last_error is not None and path.exists():
            shutil.rmtree(path, ignore_errors=True)

    def _create_manager_with_assets(
        self,
        name: str = "proj",
        *,
        include_summary: bool = True,
    ) -> tuple[ProjectManager, str, dict[str, str | None]]:
        project_root = os.path.join(self.test_dir, name)
        os.makedirs(project_root, exist_ok=True)
        pm = ProjectManager(settings_obj=self.settings_obj)
        pm.project_path = project_root  # type: ignore[assignment]

        video_path = os.path.join(project_root, "sample.mp4")
        with open(video_path, "wb") as handle:
            handle.write(b"")

        artifact_dir = os.path.join(project_root, "artifacts")
        os.makedirs(artifact_dir, exist_ok=True)

        arena_path = os.path.join(artifact_dir, "1_ProcessingArea_sample.parquet")
        rois_path = os.path.join(artifact_dir, "2_AreasOfInterest_sample.parquet")
        trajectory_path = os.path.join(artifact_dir, "3_CoordMovimento_sample.parquet")
        for path in (arena_path, rois_path, trajectory_path):
            with open(path, "wb") as handle:
                handle.write(b"data")

        summary_path = os.path.join(artifact_dir, "sample_summary.parquet")
        report_path = os.path.join(artifact_dir, "sample_report.docx")
        if include_summary:
            for path in (summary_path, report_path):
                with open(path, "wb") as handle:
                    handle.write(b"data")

        video_entry = {
            "path": video_path,
            "status": "processed",
            "has_arena": True,
            "has_rois": True,
            "has_trajectory": True,
            "has_summary": include_summary,
            "has_complete_data": True,
            "parquet_files": {
                "arena": arena_path,
                "rois": rois_path,
                "trajectory": trajectory_path,
            },
        }

        if include_summary:
            parquet_files = cast(dict[str, Any], video_entry["parquet_files"])
            parquet_files["summary"] = summary_path
            parquet_files["report_docx"] = report_path

        pm.project_data = {
            "project_name": "test",
            "project_type": "pre-recorded",
            "batches": [{"videos": [video_entry]}],
            "zones_by_video": {},
            "detection_zones": {},
        }

        zone_data = ZoneData(
            polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            roi_polygons=[[[10, 10], [50, 10], [50, 50], [10, 50]]],
            roi_names=["ROI-1"],
            roi_colors=[(255, 0, 0)],
        )
        pm.save_zone_data(zone_data, video_path=video_path, persist=False)
        pm.save_project()

        return (
            pm,
            video_path,
            {
                "arena": arena_path,
                "rois": rois_path,
                "trajectory": trajectory_path,
                "summary": summary_path if include_summary else None,
                "report": report_path if include_summary else None,
            },
        )

    def test_copy_zone_parquet_files_replicates_artifacts(self):
        pm = ProjectManager(settings_obj=self.settings_obj)
        pm.project_path = self.test_dir  # type: ignore[assignment]

        source_video = os.path.join(self.test_dir, "source.mp4")
        target_video = os.path.join(self.test_dir, "target.mp4")

        with open(source_video, "wb") as handle:
            handle.write(b"")
        with open(target_video, "wb") as handle:
            handle.write(b"")

        source_results_dir = os.path.join(self.test_dir, "source_results")
        os.makedirs(source_results_dir, exist_ok=True)

        arena_src = os.path.join(source_results_dir, "1_ProcessingArea_source.parquet")
        rois_src = os.path.join(source_results_dir, "2_AreasOfInterest_source.parquet")
        for path in (arena_src, rois_src):
            with open(path, "wb") as handle:
                handle.write(b"test")

        pm.project_data = {
            "batches": [
                {
                    "videos": [
                        {
                            "path": source_video,
                            "parquet_files": {
                                "arena": arena_src,
                                "rois": rois_src,
                            },
                            "has_arena": True,
                            "has_rois": True,
                        },
                        {
                            "path": target_video,
                            "parquet_files": {},
                            "has_arena": False,
                            "has_rois": False,
                        },
                    ]
                }
            ]
        }

        copied = pm.copy_zone_parquet_files(source_video, target_video, persist=False)

        target_parent = os.path.dirname(target_video)
        expected_parent_arena = os.path.join(target_parent, "1_ProcessingArea_target.parquet")
        expected_parent_rois = os.path.join(target_parent, "2_AreasOfInterest_target.parquet")
        hierarchical_dir = pm.resolve_results_directory("target", video_path=target_video)

        # Files should be duplicated to the parent directory
        self.assertTrue(os.path.exists(expected_parent_arena))
        self.assertTrue(os.path.exists(expected_parent_rois))
        # Alvo SEM metadados de grupo: a copia nao deve recriar a hierarquia
        # fantasma Grupo_Sem_Grupo/... (bug-sexteto live, junho 2026). O dir
        # hierarquico resolvido cai no fallback sem grupo e fica intocado.
        self.assertIn("Grupo_Sem_Grupo", str(hierarchical_dir))
        self.assertFalse(os.path.exists(str(hierarchical_dir)))

        self.assertIn("arena", copied)
        self.assertIn("rois", copied)
        self.assertEqual(os.path.normpath(copied["arena"]), os.path.normpath(expected_parent_arena))
        self.assertEqual(os.path.normpath(copied["rois"]), os.path.normpath(expected_parent_rois))

        target_entry = pm.find_video_entry(path=target_video)
        self.assertIsNotNone(target_entry)
        assert target_entry is not None
        parquet_map = target_entry.get("parquet_files", {})
        self.assertEqual(
            os.path.normpath(parquet_map.get("arena", "")),
            os.path.normpath(expected_parent_arena),
        )
        self.assertEqual(
            os.path.normpath(parquet_map.get("rois", "")),
            os.path.normpath(expected_parent_rois),
        )

    def test_zone_data_lookup_normalizes_video_paths(self):
        pm = ProjectManager(settings_obj=self.settings_obj)
        pm.project_path = self.test_dir  # type: ignore[assignment]
        pm.project_data = {"batches": []}

        video_name = "canonical_sample.mp4"
        canonical_path = os.path.join(self.test_dir, video_name)
        Path(canonical_path).write_bytes(b"")

        redundant_dir = os.path.join(
            self.test_dir,
            "..",
            os.path.basename(self.test_dir),
        )
        redundant_path = os.path.join(redundant_dir, video_name)

        pm.set_active_zone_video(redundant_path)

        zone = ZoneData(
            polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            roi_polygons=[[[10, 10], [50, 10], [50, 50], [10, 50]]],
            roi_names=["ROI-1"],
            roi_colors=[(255, 0, 0)],
        )

        pm.save_zone_data(zone, persist=False)

        pm.set_active_zone_video(canonical_path)
        retrieved = pm.get_zone_data()

        self.assertEqual(retrieved.polygon, zone.polygon)
        self.assertEqual(retrieved.roi_polygons, zone.roi_polygons)

        normalized_key = ZoneManager.normalize_video_path(canonical_path)
        self.assertIn(normalized_key, pm.project_data["zones_by_video"])

    def test_save_roi_template_persists_file_and_metadata(self):
        pm, video_path, _ = self._create_manager_with_assets()
        zone_data = pm.get_zone_data(video_path=video_path)

        metadata = pm.save_roi_template("Template Principal", zone_data)
        self.assertIsNotNone(pm.project_path)
        project_path = Path(pm.project_path or self.test_dir)

        templates = pm.list_roi_templates()
        self.assertTrue(any(t["name"] == "Template Principal" for t in templates))

        template_path = project_path / metadata["file"]
        self.assertTrue(template_path.exists())

        loaded_zone = pm.load_roi_template("Template Principal")
        self.assertEqual(loaded_zone.polygon, zone_data.polygon)
        self.assertEqual(loaded_zone.roi_polygons, zone_data.roi_polygons)

    def test_import_roi_template_registers_metadata(self):
        pm, _, _ = self._create_manager_with_assets(name="import_test")
        template_dir = Path(self.test_dir) / "external"
        template_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "version": 1,
            "name": "Template Importado",
            "data": {
                "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]],
                "roi_polygons": [],
                "roi_names": [],
                "roi_colors": [],
            },
        }

        external_path = template_dir / "import_template.json"
        external_path.write_text(json.dumps(payload), encoding="utf-8")

        metadata = pm.import_roi_template(str(external_path))
        self.assertIsNotNone(pm.project_path)
        project_path = Path(pm.project_path or self.test_dir)

        self.assertEqual(metadata["name"], "Template Importado")
        self.assertTrue((project_path / metadata["file"]).exists())

        loaded_zone = pm.load_roi_template("Template Importado")
        self.assertEqual(len(loaded_zone.polygon), 4)

    def test_import_roi_template_without_project_defaults_to_global(self):
        fake_home = Path(self.test_dir) / "single_video_home"
        fake_home.mkdir(parents=True, exist_ok=True)

        with patch.dict(
            os.environ,
            {"HOME": str(fake_home), "USERPROFILE": str(fake_home)},
        ):
            pm = ProjectManager(settings_obj=self.settings_obj)

            source_dir = Path(self.test_dir) / "single_video_import"
            source_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "version": 1,
                "name": "Template Sessao Unica",
                "data": {
                    "polygon": [
                        [0, 0],
                        [120, 0],
                        [120, 80],
                        [0, 80],
                    ],
                    "roi_polygons": [],
                    "roi_names": [],
                    "roi_colors": [],
                },
            }

            external_path = source_dir / "single_import.json"
            external_path.write_text(json.dumps(payload), encoding="utf-8")

            metadata = pm.import_roi_template(str(external_path))

            self.assertEqual(metadata["location"], "global")
            self.assertTrue(Path(metadata["file"]).exists())
            self.assertTrue(metadata.get("includes_arena"))
            self.assertFalse(metadata.get("includes_rois"))

            templates = pm.list_roi_templates()
            names = [entry["name"] for entry in templates]
            self.assertIn("Template Sessao Unica", names)

            loaded_zone = pm.load_roi_template("Template Sessao Unica")
            self.assertEqual(len(loaded_zone.polygon), 4)

            temp_video = fake_home / "video.mp4"
            temp_video.write_bytes(b"")

            pm.set_active_zone_video(str(temp_video))
            pm.save_zone_data(loaded_zone, video_path=str(temp_video), persist=False)

            restored_zone = pm.get_zone_data()
            self.assertEqual(restored_zone.polygon, loaded_zone.polygon)

    def test_list_roi_templates_includes_global_entries(self):
        fake_home = Path(self.test_dir) / "home"
        fake_home.mkdir(parents=True, exist_ok=True)

        with patch.dict(
            os.environ,
            {"HOME": str(fake_home), "USERPROFILE": str(fake_home)},
        ):
            pm, video_path, _ = self._create_manager_with_assets(name="mix")
            zone_data = pm.get_zone_data(video_path=video_path)

            pm.save_roi_template(
                "Projeto Template",
                zone_data,
                save_arena=True,
                save_rois=True,
                persist=False,
            )

            pm.roi_template_manager.save_template(
                "Global Template",
                zone_data,
                save_location="global",
                save_arena=True,
                save_rois=False,
            )

            templates = pm.list_roi_templates()
            names = [entry["name"] for entry in templates]

            self.assertIn("Projeto Template", names)
            self.assertIn("Global Template", names)

            project_entry = next(
                entry for entry in templates if entry["name"] == "Projeto Template"
            )
            global_entry = next(entry for entry in templates if entry["name"] == "Global Template")

            self.assertEqual(project_entry.get("location"), "project")
            self.assertEqual(global_entry.get("location"), "global")

    def test_scan_input_paths_uses_directory_cache(self):
        ProjectManager.clear_scan_cache()
        video_dir = os.path.join(self.test_dir, "videos")
        os.makedirs(video_dir, exist_ok=True)

        video_path = os.path.join(video_dir, "sample.mp4")
        with open(video_path, "wb") as handle:
            handle.write(b"")

        original_rglob = Path.rglob
        call_count = {"count": 0}

        def wrapped(self, pattern):
            call_count["count"] += 1
            return original_rglob(self, pattern)

        with patch("pathlib.Path.rglob", new=wrapped):
            first_scan = ProjectManager.scan_input_paths([video_dir])
            self.assertEqual(len(first_scan), 1)
            first_count = call_count["count"]

            second_scan = ProjectManager.scan_input_paths([video_dir])
            self.assertEqual(len(second_scan), 1)
            self.assertEqual(call_count["count"], first_count)

        ProjectManager.clear_scan_cache()

    @pytest.mark.slow
    def test_scan_input_paths_cache_invalidation_on_directory_change(self):
        """Test cache invalidation - marked as slow due to filesystem timestamp resolution."""
        ProjectManager.clear_scan_cache()
        video_dir = os.path.join(self.test_dir, "videos_invalidation")
        os.makedirs(video_dir, exist_ok=True)

        video_path = os.path.join(video_dir, "sample.mp4")
        with open(video_path, "wb") as handle:
            handle.write(b"")

        call_count = {"count": 0}
        original_rglob = Path.rglob

        def wrapped(self, pattern):
            call_count["count"] += 1
            return original_rglob(self, pattern)

        with patch("pathlib.Path.rglob", new=wrapped):
            initial_scan = ProjectManager.scan_input_paths([video_dir])
            self.assertEqual(len(initial_scan), 1)
            initial_count = call_count["count"]

            # Sleep needed for filesystem timestamp resolution
            # (Windows: 1s, some Linux: 1s) - intentional
            time.sleep(1.1)
            second_video = os.path.join(video_dir, "second.mp4")
            with open(second_video, "wb") as handle:
                handle.write(b"")

            updated_scan = ProjectManager.scan_input_paths([video_dir])
            self.assertEqual(len(updated_scan), 2)
            self.assertGreater(call_count["count"], initial_count)

        ProjectManager.clear_scan_cache()

    def test_create_new_live_project(self):
        """Test the creation of a new 'live' project."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        project_path = os.path.join(self.test_dir, "live_project")
        pm.create_new_project(project_path, "live")

        self.assertTrue(os.path.exists(os.path.join(project_path, CONFIG_FILE_NAME)))

        with open(os.path.join(project_path, CONFIG_FILE_NAME)) as f:
            data = json.load(f)
            self.assertEqual(data["project_name"], "live_project")
            self.assertEqual(data["project_type"], "live")
            self.assertEqual(data["batches"], [])

    def test_create_new_prerecorded_project(self):
        """Test the creation of a new 'pre-recorded' project."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        project_path = os.path.join(self.test_dir, "prerecorded_project")
        # Mock the structure that scan_input_paths would create
        video_files = [
            {"path": "/path/to/video1.mp4", "has_data": False},
            {"path": "/path/to/video2.mp4", "has_data": True},
        ]
        pm.create_new_project(project_path, "pre-recorded", video_files=video_files)

        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        self.assertTrue(os.path.exists(config_path))

        with open(config_path) as f:
            data = json.load(f)
            self.assertEqual(data["project_type"], "pre-recorded")
            self.assertEqual(len(data["batches"]), 1)
            self.assertEqual(len(data["batches"][0]["videos"]), 2)
            self.assertEqual(data["batches"][0]["videos"][0]["path"], video_files[0]["path"])
            self.assertEqual(data["batches"][0]["videos"][0]["status"], "pending")
            self.assertEqual(data["batches"][0]["videos"][1]["status"], "processed")

    def test_create_new_project_persists_the_wizard_analysis_window(self):
        """A converted v3 template's window must reach project_config.json."""
        from zebtrack.core.conditions.presets import external_trigger_preset

        window = external_trigger_preset().model_dump(mode="json", by_alias=True)
        pm = ProjectManager(settings_obj=self.settings_obj)
        project_path = os.path.join(self.test_dir, "window_project")
        pm.create_new_project(project_path, "live", use_arduino=True, analysis_window=window)

        with open(os.path.join(project_path, CONFIG_FILE_NAME)) as f:
            data = json.load(f)
        self.assertEqual(data["analysis_window"], window)
        self.assertFalse(data["external_trigger_mode"])

    def test_create_new_project_initial_model_overrides(self):
        """Project creation should initialize model overrides as inherited defaults."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        project_path = os.path.join(self.test_dir, "overrides_project")
        pm.create_new_project(project_path, "live")

        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        with open(config_path) as f:
            data = json.load(f)

        self.assertIsNone(data["analysis_window"])
        self.assertIn("model_overrides", data)
        self.assertEqual(
            data["model_overrides"],
            {
                "active_weight": None,
                "use_openvino": None,
                "device": "AUTO",
                "slot_weights": {},
                # ADR-009/012: explicit class roles, inert until the user sets them.
                "class_roles": None,
                "class_roles_weight_sha256": None,
            },
        )
        self.assertEqual(
            pm.project_data["model_overrides"],
            {
                "active_weight": None,
                "use_openvino": None,
                "device": "AUTO",
                "slot_weights": {},
                # ADR-009/012: explicit class roles, inert until the user sets them.
                "class_roles": None,
                "class_roles_weight_sha256": None,
            },
        )

    def test_add_video_batch_persists_metadata(self):
        """Video batches should persist experimental metadata and flags."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        pm.project_path = self.test_dir  # type: ignore[assignment]
        pm.project_data = {"batches": []}

        video_path = os.path.join(self.test_dir, "metadata_sample.mp4")
        with open(video_path, "wb") as handle:
            handle.write(b"sample")

        video_files = [
            {
                "path": video_path,
                "has_data": True,
                "group": "Control",
                "group_display_name": "Veiculo",
                "day": "Day01",
                "subject": "S01",
                "has_arena": True,
                "has_rois": False,
                "has_trajectory": True,
            }
        ]

        pm.add_video_batch(video_files, save_project=False)

        videos = pm.get_all_videos()
        self.assertEqual(len(videos), 1)
        video_entry = videos[0]
        self.assertEqual(video_entry["metadata"]["group"], "Control")
        self.assertEqual(video_entry["metadata"]["subject"], "S01")
        self.assertTrue(video_entry["has_arena"])
        self.assertTrue(video_entry["has_trajectory"])
        self.assertTrue(video_entry["has_complete_data"])

    def test_update_video_metadata_persists_group_day_and_subject_entries(self):
        """Existing videos should accept metadata edits without losing stored flags."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        pm.project_path = self.test_dir  # type: ignore[assignment]
        pm.project_data = {"batches": []}

        video_path = os.path.join(self.test_dir, "metadata_edit.mp4")
        with open(video_path, "wb") as handle:
            handle.write(b"sample")

        pm.add_video_batch(
            [
                {
                    "path": video_path,
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": False,
                    "metadata": {"group": "Old", "day": 1, "subject": "S01"},
                }
            ],
            save_project=False,
        )

        changed = pm.update_video_metadata(
            video_path,
            {
                "group": "Controle",
                "day": 3,
                "subject_entries": [
                    {"group": "Controle", "day": 3, "subject": "S01"},
                    {"group": "Controle", "day": 3, "subject": "S02"},
                ],
            },
            save_project=False,
        )

        self.assertTrue(changed)
        video_entry = pm.find_video_entry(path=video_path)
        self.assertIsNotNone(video_entry)
        assert video_entry is not None
        self.assertEqual(video_entry["metadata"]["group"], "Controle")
        self.assertEqual(video_entry["metadata"]["day"], 3)
        self.assertEqual(len(video_entry["metadata"]["subject_entries"]), 2)
        self.assertNotIn("subject", video_entry["metadata"])
        self.assertTrue(video_entry["has_arena"])
        self.assertTrue(video_entry["has_rois"])

    def test_update_batch_video_metadata_updates_all_descendants_once(self):
        """Batch metadata editing should update every unique video and persist once."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        pm.project_path = self.test_dir  # type: ignore[assignment]
        pm.project_data = {"batches": []}

        video_paths = []
        for index in range(2):
            video_path = os.path.join(self.test_dir, f"batch_edit_{index}.mp4")
            with open(video_path, "wb") as handle:
                handle.write(b"sample")
            video_paths.append(video_path)

        pm.add_video_batch(
            [
                {
                    "path": video_paths[0],
                    "metadata": {"group": "G1", "day": 1, "subject": "A"},
                },
                {
                    "path": video_paths[1],
                    "metadata": {"group": "G1", "day": 1, "subject": "B"},
                },
            ],
            save_project=False,
        )

        changed_count = pm.update_batch_video_metadata(
            [video_paths[0], video_paths[1], video_paths[0]],
            {"group": "G2", "day": 4},
        )

        self.assertEqual(changed_count, 2)
        for video_path in video_paths:
            video_entry = pm.find_video_entry(path=video_path)
            self.assertIsNotNone(video_entry)
            assert video_entry is not None
            self.assertEqual(video_entry["metadata"]["group"], "G2")
            self.assertEqual(video_entry["metadata"]["day"], 4)

    def test_create_project_with_animals_per_aquarium(self):
        """Test creating a project with animals_per_aquarium field."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        project_path = os.path.join(self.test_dir, "animals_test_project")
        video_files = [{"path": "video1.mp4", "has_data": False}]

        pm.create_new_project(
            project_path,
            "pre-recorded",
            video_files=video_files,
            num_aquariums=2,
            animals_per_aquarium=3,
            aquarium_width_cm=15.0,
            aquarium_height_cm=20.0,
        )

        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        self.assertTrue(os.path.exists(config_path))

        with open(config_path) as f:
            data = json.load(f)
            self.assertEqual(data["calibration"]["num_aquariums"], 2)
            self.assertEqual(data["calibration"]["animals_per_aquarium"], 3)
            self.assertEqual(data["calibration"]["aquarium_width_cm"], 15.0)
            self.assertEqual(data["calibration"]["aquarium_height_cm"], 20.0)
            self.assertIn("tracking", data)
            self.assertIn("use_single_subject_tracker", data["tracking"])
            self.assertFalse(data["tracking"]["use_single_subject_tracker"])

    def test_create_project_default_animals_per_aquarium(self):
        """Test creating a project with default animals_per_aquarium value."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        project_path = os.path.join(self.test_dir, "default_animals_project")

        pm.create_new_project(
            project_path,
            "live",
        )

        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        self.assertTrue(os.path.exists(config_path))

        with open(config_path) as f:
            data = json.load(f)
            # Check default values
            self.assertEqual(data["calibration"]["num_aquariums"], 1)
            self.assertEqual(data["calibration"]["animals_per_aquarium"], 1)
            self.assertTrue(
                data["tracking"]["use_single_subject_tracker"],
                "Expected single-subject tracker to enable for single-animal projects",
            )

    def test_create_project_persists_camera_and_arduino_settings(self):
        """Projects should persist camera index and Arduino configuration."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        project_path = os.path.join(self.test_dir, "io_settings_project")

        pm.create_new_project(
            project_path,
            "live",
            camera_index=3,
            use_arduino=True,
            arduino_port="COM7",
        )

        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        with open(config_path) as f:
            data = json.load(f)

        self.assertEqual(data["camera_index"], 3)
        self.assertTrue(data["use_arduino"])
        self.assertEqual(data["arduino_port"], "COM7")

    def test_load_project_backward_compatibility(self):
        """Test loading a project without animals_per_aquarium field."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        project_path = os.path.join(self.test_dir, "backward_compat_project")
        os.makedirs(project_path, exist_ok=True)

        # Create a project config WITHOUT animals_per_aquarium field
        # (simulates old project)
        old_project_data = {
            "project_name": "backward_compat_project",
            "project_type": "live",
            "calibration": {
                "num_aquariums": 2,
                "aquarium_width_cm": 15.0,
                "aquarium_height_cm": 20.0,
                # Missing animals_per_aquarium field
            },
            "use_openvino": False,
            "active_weight": None,
            "batches": [],
        }

        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        with open(config_path, "w") as f:
            json.dump(old_project_data, f, indent=2)

        # Load the project - should add default animals_per_aquarium value
        pm.load_project(project_path)

        self.assertEqual(pm.project_data["calibration"]["num_aquariums"], 2)
        self.assertEqual(
            pm.project_data["calibration"]["animals_per_aquarium"], 1
        )  # Default value added
        self.assertEqual(
            pm.project_data["model_overrides"],
            {
                "active_weight": None,
                "use_openvino": None,
                "device": "AUTO",
                "slot_weights": {},
                # ADR-009/012: explicit class roles, inert until the user sets them.
                "class_roles": None,
                "class_roles_weight_sha256": None,
            },
        )
        self.assertIn("tracking", pm.project_data)
        # #649: the flag follows the project's (migrated) count of 1 animal, not
        # the global setting -- which is False by default and used to turn a
        # one-animal project into a multi-subject one on its first load.
        self.assertFalse(self.settings_obj.tracking.use_single_subject_tracker)
        self.assertIs(pm.project_data["tracking"]["use_single_subject_tracker"], True)

    def test_load_project_without_tracking_derives_the_flag_from_the_animal_count(self):
        """#649: a 1-rat project opened without ``tracking`` tracks ONE subject."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        self.assertFalse(self.settings_obj.tracking.use_single_subject_tracker)
        results = {}
        for animals in (1, 3):
            project_path = os.path.join(self.test_dir, f"no_tracking_{animals}")
            os.makedirs(project_path, exist_ok=True)
            with open(os.path.join(project_path, CONFIG_FILE_NAME), "w") as f:
                json.dump(
                    {
                        "project_name": f"no_tracking_{animals}",
                        "project_type": "pre-recorded",
                        "calibration": {"num_aquariums": 1, "animals_per_aquarium": animals},
                        "batches": [],
                    },
                    f,
                )
            pm.load_project(project_path)
            results[animals] = pm.project_data["tracking"]["use_single_subject_tracker"]

        self.assertEqual(results, {1: True, 3: False})

    def test_load_project_migrates_missing_camera_and_interval_fields(self):
        """Legacy projects missing interval/camera fields should gain safe defaults."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        project_path = os.path.join(self.test_dir, "legacy_project")
        os.makedirs(project_path, exist_ok=True)

        legacy_data = {
            "project_name": "legacy_project",
            "project_type": "live",
            "calibration": {
                "num_aquariums": 1,
                "aquarium_width_cm": 10.0,
                "aquarium_height_cm": 10.0,
            },
            "use_openvino": False,
            "active_weight": None,
            "batches": [],
        }

        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        with open(config_path, "w") as f:
            json.dump(legacy_data, f, indent=2)

        pm.load_project(project_path)

        self.assertEqual(pm.project_data["analysis_interval_frames"], 10)
        self.assertEqual(pm.project_data["display_interval_frames"], 10)
        self.assertEqual(pm.project_data["camera_index"], 0)
        self.assertFalse(pm.project_data["use_arduino"])
        self.assertEqual(pm.project_data["arduino_port"], "")
        self.assertEqual(pm.project_data["calibration"]["animals_per_aquarium"], 1)
        self.assertIn("file_hash", pm.project_data)

        with open(config_path) as f:
            saved_data = json.load(f)

        for field in [
            "analysis_interval_frames",
            "display_interval_frames",
            "camera_index",
            "use_arduino",
            "arduino_port",
        ]:
            self.assertIn(field, saved_data)

        self.assertEqual(saved_data["arduino_port"], "")
        self.assertIn("file_hash", saved_data)
        self.assertEqual(
            pm.project_data["model_overrides"],
            {
                "active_weight": None,
                "use_openvino": None,
                "device": "AUTO",
                "slot_weights": {},
                # ADR-009/012: explicit class roles, inert until the user sets them.
                "class_roles": None,
                "class_roles_weight_sha256": None,
            },
        )

    def test_load_project(self):
        """Test loading an existing project configuration."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        project_path = os.path.join(self.test_dir, "load_test_project")
        video_files = [{"path": "vid1.mp4", "has_data": False}]
        pm.create_new_project(project_path, "pre-recorded", video_files=video_files)

        loader_pm = ProjectManager(settings_obj=self.settings_obj)
        loader_pm.load_project(project_path)

        self.assertEqual(loader_pm.get_project_name(), "load_test_project")
        self.assertEqual(loader_pm.get_project_type(), "pre-recorded")
        self.assertEqual(len(loader_pm.get_all_videos()), 1)

    def test_can_remove_arena_blocked_by_summary(self):
        pm, video_path, _ = self._create_manager_with_assets(
            "proj_summary_block", include_summary=True
        )

        allowed, reason = pm.can_remove_asset(video_path, "arena")

        self.assertFalse(allowed)
        self.assertIn("reports", reason or "")

    def test_remove_rois_clears_zone_and_file(self):
        pm, video_path, files = self._create_manager_with_assets(
            "proj_remove_rois", include_summary=False
        )

        allowed, _ = pm.can_remove_asset(video_path, "rois")
        self.assertTrue(allowed)

        removed = pm.remove_asset(video_path, "rois")
        self.assertTrue(removed)

        video_entry = pm.find_video_entry(path=video_path)
        assert video_entry is not None
        self.assertFalse(video_entry.get("has_rois"))
        self.assertNotIn("rois", video_entry.get("parquet_files", {}))
        rois_path = files["rois"]
        assert rois_path is not None
        self.assertFalse(os.path.exists(rois_path))
        self.assertEqual(pm.get_zone_data(video_path).roi_polygons, [])
        self.assertFalse(video_entry.get("has_complete_data"))

    def test_remove_summary_asset_clears_files(self):
        pm, video_path, files = self._create_manager_with_assets(
            "proj_remove_summary", include_summary=True
        )

        allowed, _ = pm.can_remove_asset(video_path, "summary")
        self.assertTrue(allowed)

        removed = pm.remove_asset(video_path, "summary")
        self.assertTrue(removed)

        video_entry = pm.find_video_entry(path=video_path)
        assert video_entry is not None
        self.assertFalse(video_entry.get("has_summary"))
        self.assertNotIn("summary", video_entry.get("parquet_files", {}))
        self.assertNotIn("report_docx", video_entry.get("parquet_files", {}))
        if files["summary"]:
            self.assertFalse(os.path.exists(files["summary"]))
        if files["report"]:
            self.assertFalse(os.path.exists(files["report"]))
        self.assertTrue(video_entry.get("has_complete_data"))

    def test_remove_video_requires_dependencies_removed(self):
        pm, video_path, _ = self._create_manager_with_assets(
            "proj_remove_video", include_summary=False
        )

        allowed, _ = pm.can_remove_asset(video_path, "video")
        self.assertFalse(allowed)

        pm.remove_asset(video_path, "trajectory")
        pm.remove_asset(video_path, "rois")
        pm.remove_asset(video_path, "arena")

        allowed_after, reason = pm.can_remove_asset(video_path, "video")
        self.assertTrue(allowed_after, msg=reason)

        removed = pm.remove_asset(video_path, "video", delete_files=False)
        self.assertTrue(removed)

        self.assertIsNone(pm.find_video_entry(path=video_path))
        batch_videos = pm.project_data.get("batches", [])[0]["videos"]
        self.assertEqual(len(batch_videos), 0)
        self.assertFalse(pm.project_data.get("zones_by_video"))
        self.assertTrue(os.path.exists(video_path))

    def test_load_nonexistent_project(self):
        """Test loading from a directory with no config file."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        project_path = os.path.join(self.test_dir, "nonexistent_project")
        os.makedirs(project_path, exist_ok=True)  # Create dir but no config

        with pytest.raises(ProjectInvalidError, match="not found"):
            pm.load_project(project_path)

    def test_update_video_status_and_get_next(self):
        """Test updating video status and getting the next pending video."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        project_path = os.path.join(self.test_dir, "status_project")
        video_files = [
            {"path": "video1.mp4", "has_data": False},
            {"path": "video2.mp4", "has_data": False},
            {"path": "video3.mp4", "has_data": False},
        ]
        pm.create_new_project(project_path, "pre-recorded", video_files=video_files)

        # First pending video should be video1.mp4
        next_video = pm.get_next_video()
        self.assertEqual(next_video, "video1.mp4")

        # Update status of video1 to complete
        pm.update_video_status("video1.mp4", "complete")

        # Now the next pending video should be video2.mp4
        next_video = pm.get_next_video()
        self.assertEqual(next_video, "video2.mp4")

        # Verify that the change was saved by loading it into a new instance
        loader_pm = ProjectManager(settings_obj=self.settings_obj)
        loader_pm.load_project(project_path)
        all_videos = loader_pm.get_all_videos()
        self.assertEqual(all_videos[0]["status"], "complete")
        self.assertEqual(loader_pm.get_next_video(), "video2.mp4")

        # Mark all as complete
        pm.update_video_status("video2.mp4", "complete")
        pm.update_video_status("video3.mp4", "complete")

        # Now there should be no pending videos
        self.assertIsNone(pm.get_next_video())

        # Now there should be no pending videos
        self.assertIsNone(pm.get_next_video())

    def test_project_manager_script(self):
        """Test the ProjectManager using the original script-based test."""
        # Setup test directory
        test_dir = os.path.join(self.test_dir, "pm_test_project")
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        pm = ProjectManager(settings_obj=self.settings_obj)

        # 1. Test creating a new pre-recorded project
        # Using a platform-independent path for testing
        video_files = [
            {"path": os.path.join("C:", "videos", "vid1.mp4"), "has_data": False},
            {"path": os.path.join("C:", "videos", "vid2.mp4"), "has_data": False},
        ]
        pm.create_new_project(test_dir, "pre-recorded", video_files=video_files)

        # 2. Test loading an existing project
        pm_loader = ProjectManager(settings_obj=self.settings_obj)
        pm_loader.load_project(test_dir)

        # 3. Test updating and getting next video
        next_vid = pm_loader.get_next_video()
        self.assertIsNotNone(next_vid)
        assert next_vid is not None

        pm_loader.update_video_status(next_vid, "complete")

        next_vid_after_update = pm_loader.get_next_video()
        self.assertNotEqual(next_vid, next_vid_after_update)

    def test_register_processing_outputs_updates_flags(self):
        pm = ProjectManager(settings_obj=self.settings_obj)
        pm.project_path = self.test_dir  # type: ignore[assignment]
        video_path = os.path.join(self.test_dir, "metadata_sample.mp4")
        pm.project_data = {
            "batches": [
                {
                    "videos": [
                        {
                            "path": video_path,
                            "status": "pending",
                            "has_arena": True,
                            "has_rois": True,
                            "has_trajectory": False,
                            "has_complete_data": False,
                            "parquet_files": {},
                        }
                    ]
                }
            ]
        }

        pm.save_project = MagicMock(return_value=True)

        results_dir = os.path.join(self.test_dir, "metadata_sample_results")
        trajectory_path = os.path.join(results_dir, "3_CoordMovimento_metadata_sample.parquet")
        summary_path = os.path.join(results_dir, "metadata_sample_summary.parquet")
        excel_path = os.path.join(results_dir, "metadata_sample_summary.xlsx")
        report_path = os.path.join(results_dir, "metadata_sample_report.docx")

        updated = pm.register_processing_outputs(
            video_path,
            results_dir=results_dir,
            trajectory_path=trajectory_path,
            summary_parquet=summary_path,
            summary_excel=excel_path,
            report_path=report_path,
        )

        self.assertTrue(updated)
        video_entry = pm.project_data["batches"][0]["videos"][0]
        self.assertTrue(video_entry.get("has_trajectory"))
        self.assertTrue(video_entry.get("has_summary"))
        self.assertTrue(video_entry.get("has_complete_data"))
        # Paths are stored as POSIX format in project_data
        from pathlib import Path

        self.assertEqual(video_entry.get("results_dir"), Path(results_dir).as_posix())
        self.assertEqual(
            video_entry["parquet_files"].get("trajectory"), Path(trajectory_path).as_posix()
        )
        self.assertEqual(video_entry["parquet_files"].get("summary"), Path(summary_path).as_posix())
        self.assertEqual(
            video_entry["parquet_files"].get("summary_excel"), Path(excel_path).as_posix()
        )
        self.assertEqual(
            video_entry["parquet_files"].get("report_docx"), Path(report_path).as_posix()
        )
        pm.save_project.assert_called_once()

    def test_derive_processing_metadata_falls_back_to_project_entry(self):
        pm = ProjectManager(settings_obj=self.settings_obj)
        video_path = os.path.join(self.test_dir, "GroupA_subject4.mp4")
        pm.project_data = {
            "batches": [
                {
                    "videos": [
                        {
                            "path": video_path,
                            "metadata": {"group": "GroupA"},
                            "day": 2,
                            "subject": "4",
                        }
                    ]
                }
            ]
        }

        metadata = pm.derive_processing_metadata(
            "GroupA_subject4",
            video_path,
        )

        self.assertEqual(metadata["experiment_id"], "GroupA_subject4")
        self.assertEqual(metadata["video_name"], "GroupA_subject4")
        self.assertEqual(metadata["group"], "GroupA")
        self.assertEqual(metadata["day"], 2)
        self.assertEqual(metadata["subject"], "4")
        self.assertEqual(metadata["group_id"], "GroupA")

    def test_derive_processing_metadata_defaults_when_missing(self):
        pm = ProjectManager(settings_obj=self.settings_obj)
        pm.project_data = {"batches": []}

        metadata = pm.derive_processing_metadata("CECT_4", None)

        self.assertEqual(metadata["experiment_id"], "CECT_4")
        self.assertEqual(metadata["video_name"], "CECT_4")
        self.assertNotIn("group", metadata)

    def test_detector_state_persistence(self):
        """Test detector state save and retrieve functionality."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        project_path = os.path.join(self.test_dir, "detector_state_project")

        # Create a new project first
        pm.create_new_project(project_path, "live")

        # Test saving detector state
        detector_config = {
            "plugin_name": "YOLO (Ultralytics)",
            "confidence_threshold": 0.7,
            "nms_threshold": 0.5,
            "context": "tracking",
        }

        save_result = pm.save_detector_state(detector_config)
        self.assertTrue(save_result)

        # Test retrieving detector state
        retrieved_config = pm.get_detector_state()
        self.assertIsNotNone(retrieved_config)
        self.assertEqual(retrieved_config["plugin_name"], "YOLO (Ultralytics)")
        self.assertEqual(retrieved_config["confidence_threshold"], 0.7)
        self.assertEqual(retrieved_config["nms_threshold"], 0.5)
        self.assertEqual(retrieved_config["context"], "tracking")
        self.assertIn("last_updated", retrieved_config)

        # Test loading project and verifying detector state persists
        loader_pm = ProjectManager(settings_obj=self.settings_obj)
        loader_pm.load_project(project_path)

        loaded_config = loader_pm.get_detector_state()
        self.assertEqual(loaded_config["plugin_name"], "YOLO (Ultralytics)")
        self.assertEqual(loaded_config["confidence_threshold"], 0.7)
        self.assertEqual(loaded_config["context"], "tracking")

    def test_detector_state_empty_project(self):
        """Test detector state retrieval from empty project returns empty dict."""
        pm = ProjectManager(settings_obj=self.settings_obj)
        project_path = os.path.join(self.test_dir, "empty_detector_project")

        # Create a new project without detector config
        pm.create_new_project(project_path, "live")

        # Should return empty dict when no detector config exists
        config = pm.get_detector_state()
        self.assertEqual(config, {})

    def test_detector_state_save_without_project(self):
        """Test detector state saving fails without project data."""
        pm = ProjectManager(settings_obj=self.settings_obj)

        detector_config = {"plugin_name": "OpenVINO", "confidence_threshold": 0.6}

        # Should fail when no project data exists
        result = pm.save_detector_state(detector_config)
        self.assertFalse(result)

    def test_load_project_forgets_the_previous_active_zone_video(self):
        """Regression: an ad-hoc single-video session leaked into the next project.

        ``_active_zone_video`` / ``_last_zone_source_video`` are INSTANCE state
        on ``ZoneManager``, and ``load_project`` swaps ``project_path`` and
        ``project_data`` without touching it. The freshly opened project
        therefore inherited the pointer left by whatever ran before it, and
        ``ProjectLifecycleCoordinator`` fed THAT video's zones into
        ``DetectorService.configure_zones``.
        """
        pm = ProjectManager(settings_obj=self.settings_obj)
        project_path = os.path.join(self.test_dir, "zone_pointer_project")
        pm.create_new_project(project_path, "pre-recorded", video_files=[])

        # Stand in for the single-video workflow: it points the zone manager at
        # a video that has nothing to do with the project about to be opened.
        loader_pm = ProjectManager(settings_obj=self.settings_obj)
        loader_pm.set_active_zone_video("C:/elsewhere/AdHoc/CECT_4.mp4")
        assert loader_pm.get_active_zone_video() is not None

        loader_pm.load_project(project_path)

        self.assertIsNone(loader_pm.get_active_zone_video())
        self.assertIsNone(loader_pm.zone_manager._last_zone_source_video)


if __name__ == "__main__":
    unittest.main()


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


def test_apply_project_migrations_normalizes_analysis_parameters(project_manager):
    """Old projects get the dict, but NO invented values.

    Stamping numbers here from the session settings would freeze the very leak
    ``analysis_parameters`` exists to close: an ad-hoc run may already have
    rewritten the shared object. Absent means "use the session baseline".
    """
    loaded: dict[str, Any] = {"calibration": {}, "analysis_profiles": [], "tracking": {}}

    migrated_data, migrated, fields = project_manager._apply_project_migrations(
        loaded,
        structlog.get_logger().bind(test="analysis_parameters_migration"),
    )

    assert migrated is True
    assert "analysis_parameters" in fields
    assert migrated_data["analysis_parameters"] == {}


def test_apply_project_migrations_keeps_declared_analysis_parameters(project_manager):
    loaded = {
        "calibration": {},
        "analysis_profiles": [],
        "tracking": {},
        "analysis_parameters": {"freezing_vel_threshold": 3.25},
    }

    migrated_data, _migrated, fields = project_manager._apply_project_migrations(
        loaded,
        structlog.get_logger().bind(test="analysis_parameters_kept"),
    )

    assert migrated_data["analysis_parameters"] == {"freezing_vel_threshold": 3.25}
    assert "analysis_parameters" not in fields


def test_apply_project_migrations_repairs_hand_edited_analysis_parameters(project_manager):
    """A JSON edited by hand can put anything there; readers need a dict."""
    loaded = {
        "calibration": {},
        "analysis_profiles": [],
        "tracking": {},
        "analysis_parameters": "nonsense",
    }

    migrated_data, migrated, fields = project_manager._apply_project_migrations(
        loaded,
        structlog.get_logger().bind(test="analysis_parameters_repair"),
    )

    assert migrated is True
    assert "analysis_parameters" in fields
    assert migrated_data["analysis_parameters"] == {}


def test_apply_project_migrations_initializes_slot_weights(project_manager):
    loaded = {
        "calibration": {},
        "analysis_profiles": [],
        "tracking": {},
        "model_overrides": {
            "active_weight": None,
            "use_openvino": None,
            "device": "AUTO",
        },
    }

    migrated_data, migrated, fields = project_manager._apply_project_migrations(
        loaded,
        structlog.get_logger().bind(test="slot_weights_migration"),
    )

    assert migrated is True
    assert "model_overrides" in fields
    assert migrated_data["model_overrides"]["slot_weights"] == {}


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


def test_get_completed_sessions_canonicalizes_group_names(project_manager):
    """Grupos com espaço/caractere especial ("Tratamento 1") viram pasta
    sanitizada ("Grupo_Tratamento_1"); o scan devolve "Tratamento_1". O
    ProjectManager deve mapear de volta ao nome do projeto para que a grade de
    progresso e o diálogo de bloco reconheçam a sessão como concluída.
    """
    project_manager.project_data["groups"] = ["Controle", "Tratamento 1"]

    raw = {
        (1, "Controle", "1"),
        (1, "Tratamento_1", "2"),
    }
    with patch(
        "zebtrack.core.project.metadata_manager.MetadataManager.get_completed_sessions",
        return_value=raw,
    ):
        result = project_manager.get_completed_sessions()

    assert (1, "Tratamento 1", "2") in result
    assert (1, "Controle", "1") in result
    assert (1, "Tratamento_1", "2") not in result


def test_get_completed_sessions_without_groups_returns_raw(project_manager):
    """Sem grupos definidos, retorna o resultado do scan inalterado."""
    project_manager.project_data.pop("groups", None)
    raw = {(1, "Qualquer", "1")}
    with patch(
        "zebtrack.core.project.metadata_manager.MetadataManager.get_completed_sessions",
        return_value=raw,
    ):
        assert project_manager.get_completed_sessions() == raw


# ---------------------------------------------------------------------------
# detection_zones: espelho global do save por vídeo
# ---------------------------------------------------------------------------
#
# ``detection_zones`` é o default do projeto que ``get_zone_data(
# fallback_to_global=True)`` serve a qualquer vídeo sem zonas próprias.
# Espelhar TODO save por vídeo nele é o que transformava a arena de um vídeo na
# arena de todos os outros. Live continua precisando do espelho (uma câmera, uma
# arena, e o .mp4 gravado não tem chave própria); pré-gravado, não.


def _zone(polygon):
    from zebtrack.core.detection import ZoneData

    return ZoneData(polygon=list(polygon), roi_polygons=[], roi_names=[], roi_colors=[])


ARENA_A = [[0, 0], [10, 0], [10, 10], [0, 10]]
ARENA_B = [[5, 5], [20, 5], [20, 20], [5, 20]]


def test_prerecorded_per_video_save_does_not_rewrite_global_default(project_manager):
    """Projeto pré-gravado: salvar zonas de um vídeo não toca o default global."""
    project_manager.project_data["project_type"] = "pre-recorded"

    project_manager.save_zone_data(_zone(ARENA_A), "video_a.mp4", persist=False)

    assert project_manager.project_data["detection_zones"] == {}
    stored = project_manager.get_zone_data("video_a.mp4", fallback_to_global=False)
    assert stored.polygon == ARENA_A


def test_prerecorded_second_video_does_not_inherit_the_first_arena(project_manager):
    """A regressão em si: abrir o vídeo B não pode devolver a arena do vídeo A.

    Antes, o save de A escrevia ``detection_zones`` e o fallback global entregava
    aquela geometria para B — a análise rodava e o relatório saía completo,
    medido contra a arena errada.
    """
    project_manager.project_data["project_type"] = "pre-recorded"
    project_manager.save_zone_data(_zone(ARENA_A), "video_a.mp4", persist=False)

    inherited = project_manager.get_zone_data("video_b.mp4", fallback_to_global=True)

    assert not inherited.polygon


def test_live_project_still_mirrors_zones_into_the_global_default(project_manager):
    """Contrato do fluxo live: uma arena para o projeto inteiro.

    As zonas ficam sob a chave do ``live_camera_reference_frame.png`` e os
    ``.mp4`` gravados não têm chave própria, então ``ZoneContextService``,
    ``ValidationManager`` e a grade de sessões planejadas leem o global. Sem o
    espelho, um projeto live esqueceria a calibração.
    """
    project_manager.project_data["project_type"] = "live"

    project_manager.save_zone_data(_zone(ARENA_B), "live_camera_reference_frame.png", persist=False)

    assert project_manager.project_data["detection_zones"]["polygon"] == ARENA_B
    recorded = project_manager.get_zone_data("sessao_gravada.mp4", fallback_to_global=True)
    assert recorded.polygon == ARENA_B


def test_project_without_declared_type_keeps_legacy_mirror(project_manager):
    """Vídeo único e live ad-hoc rodam sem ``project_type``: comportamento intacto."""
    project_manager.project_data.pop("project_type", None)

    project_manager.save_zone_data(_zone(ARENA_A), "avulso.mp4", persist=False)

    assert project_manager.project_data["detection_zones"]["polygon"] == ARENA_A


def test_save_without_target_video_is_still_the_global_save(project_manager):
    """Sem vídeo alvo o save É o global — inclusive em projeto pré-gravado."""
    project_manager.project_data["project_type"] = "pre-recorded"
    project_manager.zone_manager.set_active_zone_video(project_manager.project_data, None)

    project_manager.save_zone_data(_zone(ARENA_B), None, persist=False)

    assert project_manager.project_data["detection_zones"]["polygon"] == ARENA_B


class TestProjectManagerExtended:
    def test_config_file_name_constant(self):
        assert CONFIG_FILE_NAME == "project_config.json"

    def test_initialization_with_dependencies(self):
        state_mgr = StateManager()
        settings_mock = MagicMock()
        pm = ProjectManager(state_manager=state_mgr, settings_obj=settings_mock)

        assert pm.state_manager is state_mgr
        assert pm.settings is settings_mock
        assert pm.project_path is None
        assert pm.project_data == {}
        assert pm._groups_cache_valid is False

    def test_threadsafe_decorator(self):
        class Dummy:
            def __init__(self):
                import threading

                self._lock = threading.RLock()
                self.calls = 0

            @_threadsafe
            def increment(self):
                self.calls += 1
                return self.calls

        d = Dummy()
        assert d.increment() == 1
        assert d.increment() == 2

    def test_save_roi_template_without_project_raises(self):
        pm = ProjectManager()
        pm.project_path = None
        zone_data = ZoneData(polygon=[[0, 0], [100, 0], [100, 100], [0, 100]])

        with pytest.raises(ValueError, match="Cannot save the template into the current project"):
            pm.save_roi_template("my_template", zone_data, save_location="project")

    def test_zone_data_to_and_from_dict_delegation(self):
        pm = ProjectManager()
        zone_data = ZoneData(
            polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            roi_polygons=[[[10, 10], [20, 10], [20, 20], [10, 20]]],
            roi_names=["zone1"],
            roi_colors=[(255, 0, 0)],
        )
        serialized = pm._zone_data_to_dict(zone_data)
        assert "polygon" in serialized or "arena" in serialized or "roi_polygons" in serialized

        restored = pm._zone_data_from_dict(serialized)
        assert restored is not None
        assert len(restored.polygon) == 4
        assert "zone1" in restored.roi_names


class TestProjectManagerExtended2:
    def test_constants(self):
        assert CONFIG_FILE_NAME == "project_config.json"

    def test_threadsafe_decorator(self):
        class Dummy:
            def __init__(self):
                self._lock = MagicMock()
                self.called = False

            @_threadsafe
            def safe_method(self, arg):
                self.called = True
                return arg * 2

        d = Dummy()
        res = d.safe_method(21)
        assert res == 42
        assert d.called is True
        d._lock.__enter__.assert_called_once()
        d._lock.__exit__.assert_called_once()

    def test_save_roi_template_no_project_loaded_raises(self):
        pm = ProjectManager()
        pm.project_path = None
        zone = ZoneData(polygon=[[0, 0], [10, 0], [10, 10], [0, 10]])

        with pytest.raises(ValueError, match="no project loaded"):
            pm.save_roi_template("MyTemplate", zone, save_location="project")

    def test_zone_data_serialization_delegation(self):
        pm = ProjectManager()
        zone = ZoneData(
            polygon=[[0, 0], [10, 0], [10, 10], [0, 10]],
            roi_polygons=[[[1, 1], [2, 2], [1, 2]]],
            roi_names=["R1"],
        )
        d = pm._zone_data_to_dict(zone)
        assert "polygon" in d
        assert "roi_names" in d

        restored = pm._zone_data_from_dict(d)
        assert list(restored.polygon) == [[0, 0], [10, 0], [10, 10], [0, 10]]
        assert "R1" in list(restored.roi_names)

    def test_get_aquarium_asset_flags_none_path(self):
        pm = ProjectManager()
        flags = pm.get_aquarium_asset_flags(None, 0)
        assert flags["has_arena"] is False
        assert flags["has_rois"] is False
        assert flags["has_trajectory"] is False
        assert flags["has_summary"] is False
        assert flags["has_complete_data"] is False

    def test_has_assets_none_path(self):
        pm = ProjectManager()
        pm.find_video_entry = MagicMock(return_value=None)  # type: ignore[method-assign]

        assert pm.has_arena_data(None) is False
        assert pm.has_roi_data(None) is False
        assert pm.has_trajectory_data(None) is False
        assert pm.has_summary_data(None) is False


class TestProjectManagerExtended6:
    def test_save_roi_template_no_project_raises(self):
        pm = ProjectManager()
        pm.project_path = None
        zone_data = MagicMock()

        with pytest.raises(ValueError, match="no project loaded"):
            pm.save_roi_template("Template1", zone_data, save_location="project")

    def test_project_manager_initial_cache_state(self):
        pm = ProjectManager()
        assert pm._groups_cache is None
        assert pm._groups_cache_valid is False

    def test_get_available_groups_cached(self):
        pm = ProjectManager()
        pm._groups_cache = ["Control", "Treated"]
        pm._groups_cache_valid = True

        assert pm.get_available_groups() == ["Control", "Treated"]

    def test_invalidate_groups_cache(self):
        pm = ProjectManager()
        pm._groups_cache = ["Control", "Treated"]
        pm._groups_cache_valid = True

        pm.invalidate_groups_cache()
        assert pm._groups_cache is None
        assert pm._groups_cache_valid is False

    def test_get_project_type(self):
        pm = ProjectManager()
        pm.project_data = {"project_type": "live"}
        assert pm.get_project_type() == "live"

        pm.project_data = {}
        assert pm.get_project_type() is None


class TestProjectManagerExtended7:
    def test_is_multi_aquarium_video_none(self):
        pm = ProjectManager()
        assert pm.is_multi_aquarium_video(None) is False

    def test_is_multi_aquarium_video_true(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.zone_manager.is_multi_aquarium_video.return_value = True
        assert pm.is_multi_aquarium_video("/videos/video1.mp4") is True

    def test_get_aquarium_count_none(self):
        pm = ProjectManager()
        assert pm.get_aquarium_count(None) == 1

    def test_get_aquarium_count_two(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.zone_manager.get_aquarium_count.return_value = 2
        assert pm.get_aquarium_count("/videos/video1.mp4") == 2

    def test_clear_multi_aquarium_zone_data_none(self):
        pm = ProjectManager()
        pm.clear_multi_aquarium_zone_data(None)

    def test_update_main_polygon_delegates_to_zone_manager(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.project_data = {"zones": {}}

        points = [(10, 10), (20, 20), (30, 10)]
        pm.update_main_polygon(points)
        pm.zone_manager.update_main_polygon.assert_called_once_with(
            pm.project_data, points, persist_callback=pm.save_project
        )


class TestProjectManagerExtended8:
    def test_register_multi_aquarium_outputs_empty(self):
        pm = ProjectManager()
        pm.project_data = {"outputs": {}}

        pm.register_multi_aquarium_outputs("/videos/video1.mp4", {})
        assert pm.project_data["outputs"] == {}

    def test_project_manager_initial_state(self):
        pm = ProjectManager()
        assert pm.project_path is None
        assert pm.project_data == {}
        assert pm.metadata is None
        assert pm._groups_cache is None
        assert pm._groups_cache_valid is False

    def test_list_roi_templates_delegates_to_asset_manager(self):
        pm = ProjectManager()
        pm.asset_manager = MagicMock()
        pm.asset_manager.list_roi_templates.return_value = [{"name": "Template1"}]

        res = pm.list_roi_templates(include_global=True)
        assert res == [{"name": "Template1"}]
        pm.asset_manager.list_roi_templates.assert_called_once_with(
            pm.project_data, include_global=True
        )

    def test_clear_multi_aquarium_zone_data_none_safe(self):
        pm = ProjectManager()
        # Passing None should return immediately without accessing zone_manager
        pm.clear_multi_aquarium_zone_data(None)


class TestProjectManagerExtended9:
    def test_update_main_polygon_delegates_to_zone_manager(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.project_data = {}

        points = [(0, 0), (10, 0), (10, 10), (0, 10)]
        pm.update_main_polygon(points)

        pm.zone_manager.update_main_polygon.assert_called_once_with(
            pm.project_data, points, persist_callback=pm.save_project
        )

    def test_metadata_manager_initialized(self):
        pm = ProjectManager()
        assert pm.metadata_manager is not None
        assert pm.lifecycle_manager is not None

    def test_get_aquarium_count_none_safe(self):
        pm = ProjectManager()
        assert pm.get_aquarium_count(None) == 1


class TestProjectManagerExtended10:
    def test_project_manager_get_zone_data_delegation(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.project_data = {"test": True}

        pm.get_zone_data(video_path="/path/vid.mp4", fallback_to_global=False)
        pm.zone_manager.get_zone_data.assert_called_once_with(
            pm.project_data, video_path="/path/vid.mp4", fallback_to_global=False
        )

    def test_project_manager_get_multi_aquarium_zone_data_delegation(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.project_data = {"test": True}

        pm.get_multi_aquarium_zone_data(video_path="/path/vid.mp4")
        pm.zone_manager.get_multi_aquarium_zone_data.assert_called_once_with(
            pm.project_data, "/path/vid.mp4"
        )

    def test_project_manager_config_file_name_constant(self):
        assert CONFIG_FILE_NAME == "project_config.json"

    def test_project_manager_default_project_data(self):
        pm = ProjectManager()
        assert isinstance(pm.project_data, dict)
        assert pm.asset_manager is not None
        assert pm.zone_manager is not None


# ---------------------------------------------------------------------------
# TASK-087: a real project on disk, edited through the facade and reloaded.
# ---------------------------------------------------------------------------


SQUARE = [[0, 0], [10, 0], [10, 10], [0, 10]]


def _disk_project(tmp_path, *videos: dict) -> ProjectManager:
    pm = ProjectManager(settings_obj=None)
    pm.create_new_project(
        tmp_path / "proj", "Pre-recorded", video_files=list(videos), group_names=["A", "B"]
    )
    return pm


def _reloaded(pm: ProjectManager) -> dict:
    fresh = ProjectManager(settings_obj=None)
    fresh.load_project(pm.project_path)
    return fresh.project_data


def _video(tmp_path, rel: str, **meta) -> dict:
    path = (tmp_path / rel).as_posix()
    return {"path": path, **meta}


class TestUpdateVideoMetadata:
    def test_group_and_day_update_is_persisted_with_the_last_session(self, tmp_path):
        video = _video(tmp_path, "v1.mp4", group="A", day=1, subject="S1")
        pm = _disk_project(tmp_path, video)

        assert pm.update_video_metadata(video["path"], {"group": " B ", "day": "3"}) is True

        entry = _reloaded(pm)["batches"][0]["videos"][0]
        assert entry["metadata"] == {"group": "B", "group_id": "B", "day": 3, "subject": "S1"}
        assert (entry["group"], entry["day"]) == ("B", 3)
        assert (_reloaded(pm)["last_selected_day"], _reloaded(pm)["last_selected_group"]) == (
            3,
            "B",
        )

    def test_blank_values_remove_the_fields(self, tmp_path):
        video = _video(tmp_path, "v1.mp4", group="A", day=2, subject="S1")
        pm = _disk_project(tmp_path, video)

        changed = pm.update_video_metadata(
            Path(video["path"]), {"group": "", "day": 0, "subject": "  "}
        )

        assert changed is True
        entry = _reloaded(pm)["batches"][0]["videos"][0]
        assert "metadata" in entry and entry["metadata"] == {}
        assert not {"group", "day", "subject"} & set(entry)

    def test_subject_entries_set_multi_subject_and_clear_the_single_subject(self, tmp_path):
        video = _video(tmp_path, "v1.mp4", subject="S1")
        pm = _disk_project(tmp_path, video)
        entries = [
            {"group": " A ", "day": "2", "subject": " 7 "},
            "junk",
            {"group": "B", "day": -1, "subject": 8, "aquarium_id": 5},
        ]

        assert pm.update_video_metadata(video["path"], {"subject_entries": entries}) is True

        meta = pm.find_video_entry(path=video["path"])["metadata"]  # type: ignore[index]
        assert meta["subject_entries"] == [
            {"group": "A", "day": 2, "subject": "7", "aquarium_id": 0},
            {"group": "B", "day": None, "subject": "8", "aquarium_id": 5},
        ]
        assert meta["is_multi_subject"] is True
        assert "subject" not in meta

    def test_a_single_subject_entry_becomes_the_subject(self, tmp_path):
        video = _video(tmp_path, "v1.mp4")
        pm = _disk_project(tmp_path, video)

        pm.update_video_metadata(
            video["path"], {"subject_entries": [{"subject": "9"}]}, save_project=False
        )

        entry = pm.find_video_entry(path=video["path"])
        assert entry["subject"] == "9"  # type: ignore[index]
        assert entry["is_multi_subject"] is False  # type: ignore[index]
        assert "metadata" not in _reloaded(pm)["batches"][0]["videos"][0]

    def test_clearing_subject_entries(self, tmp_path):
        video = _video(tmp_path, "v1.mp4")
        pm = _disk_project(tmp_path, video)
        pm.update_video_metadata(video["path"], {"subject_entries": [{"subject": "1"}, {}]})

        assert pm.update_video_metadata(video["path"], {"subject_entries": []}) is True

        entry = pm.find_video_entry(path=video["path"])
        assert not {"subject_entries", "is_multi_subject"} & set(entry["metadata"])  # type: ignore[index]
        assert "subject_entries" not in entry  # type: ignore[operator]

    def test_repeating_an_update_and_unknown_videos_report_no_change(self, tmp_path):
        video = _video(tmp_path, "v1.mp4", group="A")
        pm = _disk_project(tmp_path, video)
        pm.update_video_metadata(video["path"], {"group": "B"})

        assert pm.update_video_metadata(video["path"], {"group": "B"}) is False
        assert pm.update_video_metadata(tmp_path / "ghost.mp4", {"group": "B"}) is False

    def test_batch_update_counts_unique_videos_and_saves_once(self, tmp_path):
        first = _video(tmp_path, "v1.mp4", group="A")
        second = _video(tmp_path, "v2.mp4", group="B")
        pm = _disk_project(tmp_path, first, second)
        saves: list[int] = []
        original_save = pm.save_project
        pm.save_project = lambda: (saves.append(1), original_save())  # type: ignore[func-returns-value, method-assign]

        count = pm.update_batch_video_metadata(
            [first["path"], Path(first["path"]), second["path"]], {"group": "B", "day": 4}
        )

        assert count == 2
        assert saves == [1]
        assert _reloaded(pm)["last_selected_day"] == 4
        assert pm.update_batch_video_metadata([second["path"]], {"subject": "S3"}) == 1
        assert saves == [1, 1]
        pm.project_path = None
        assert pm.update_batch_video_metadata([second["path"]], {"subject": "S4"}) == 1
        assert saves == [1, 1]


class TestHierarchyRemoval:
    @staticmethod
    def _videos(tmp_path):
        return [
            _video(tmp_path, "A1/s1.mp4", group="A", day=1, subject="1"),
            _video(tmp_path, "A1/s2.mp4", group="A", day=1, subject="2"),
            _video(tmp_path, "A2/s1.mp4", group="A", day=2, subject="1"),
            _video(tmp_path, "B1/s1.mp4", group="B", day=1, subject="1"),
        ]

    def test_remove_subject_only_touches_that_group_day_and_subject(self, tmp_path):
        pm = _disk_project(tmp_path, *self._videos(tmp_path))
        groups_before = pm.get_available_groups()

        assert pm.remove_subject("A", "1", "1", delete_files=False) == (1, 0)

        remaining = [v["path"].rsplit("/", 2)[-2:] for v in _reloaded(pm)["batches"][0]["videos"]]
        assert remaining == [["A1", "s2.mp4"], ["A2", "s1.mp4"], ["B1", "s1.mp4"]]
        assert pm.get_available_groups() == groups_before == ["A", "B"]
        assert pm.remove_subject("A", "9", "1", delete_files=False) == (0, 0)

    def test_remove_day_and_group(self, tmp_path):
        pm = _disk_project(tmp_path, *self._videos(tmp_path))

        assert pm.remove_day("A", "1", delete_files=False) == (2, 0)
        assert pm.remove_group("A", delete_files=False) == (1, 0)

        assert [v["metadata"]["group"] for v in pm.get_all_videos()] == ["B"]

    def test_multi_subject_video_loses_only_that_subjects_aquarium(self, tmp_path):
        video = _video(tmp_path, "multi.mp4", group="A", day=1, subject="2")
        pm = _disk_project(tmp_path, video)
        entry = pm.find_video_entry(path=video["path"])
        entry["multi_aquarium_mode"] = True  # type: ignore[index]
        entry["multi_aquarium_outputs"] = {  # type: ignore[index]
            "0": {"subject_id": "1", "parquet_files": {"trajectory": "t0"}},
            "1": {"subject_id": "2", "parquet_files": {}},
        }

        assert pm.remove_subject("A", "1", "2", delete_files=False) == (1, 0)

        assert list(entry["multi_aquarium_outputs"]) == ["0"]  # type: ignore[index]
        assert pm.find_video_entry(path=video["path"]) is entry

    def test_multi_subject_video_without_a_matching_aquarium_is_a_failure(self, tmp_path):
        video = _video(tmp_path, "multi.mp4", group="A", day=1, subject="5")
        pm = _disk_project(tmp_path, video)
        pm.find_video_entry(path=video["path"])["multi_aquarium_outputs"] = {  # type: ignore[index]
            "0": {"subject_id": "1"},
            "1": {"subject_id": "2"},
        }

        assert pm.remove_subject("A", "1", "5", delete_files=False) == (0, 1)

    def test_aquarium_lookup_by_subject_then_by_key(self):
        entry = {"multi_aquarium_outputs": {"0": {"subject_id": "S7"}, "3": {}}}

        assert ProjectManager._find_aquarium_for_subject(entry, "S7") == 0
        assert ProjectManager._find_aquarium_for_subject(entry, "3") == 3
        assert ProjectManager._find_aquarium_for_subject(entry, "x") is None
        assert ProjectManager._find_aquarium_for_subject({}, "x") is None


class TestAquariumScopes:
    @staticmethod
    def _two_tank_project(tmp_path):
        video = _video(tmp_path, "tanks.mp4")
        pm = _disk_project(tmp_path, video)
        pm.save_multi_aquarium_zone_data(
            video["path"],
            MultiAquariumZoneData(
                aquariums=[
                    AquariumData(id=0, polygon=SQUARE, subject_id="S1"),
                    AquariumData(id=1, polygon=SQUARE, roi_polygons=[SQUARE], subject_id="S2"),
                ]
            ),
        )
        entry = pm.find_video_entry(path=video["path"])
        entry["multi_aquarium_mode"] = True  # type: ignore[index]
        entry["multi_aquarium_outputs"] = {  # type: ignore[index]
            "0": {"subject_id": "S1", "parquet_files": {"trajectory": "t0"}},
            "1": {"subject_id": "S2", "parquet_files": {"trajectory": "t1", "summary": "s1"}},
        }
        return pm, video["path"], entry

    def test_aquarium_flags_come_from_that_aquarium(self, tmp_path):
        pm, path, _entry = self._two_tank_project(tmp_path)

        assert pm.get_aquarium_asset_flags(path, 0) == {
            "has_arena": True,
            "has_rois": False,
            "has_trajectory": True,
            "has_summary": False,
            "has_complete_data": False,
        }
        assert pm.get_aquarium_asset_flags(path, 1)["has_complete_data"] is True
        assert pm.get_aquarium_asset_flags(None, 0)["has_arena"] is False
        assert pm.is_multi_aquarium_video(path) is True
        assert pm.get_aquarium_count(path) == 2

    def test_single_video_aquarium_flags_fall_back_to_the_entry(self, tmp_path):
        video = _video(tmp_path, "single.mp4")
        pm = _disk_project(tmp_path, video)
        pm.find_video_entry(path=video["path"]).update(has_arena=True, has_trajectory=True)  # type: ignore[union-attr]

        flags = pm.get_aquarium_asset_flags(video["path"], 0)

        assert (flags["has_arena"], flags["has_rois"], flags["has_trajectory"]) == (
            True,
            False,
            True,
        )

    def test_removing_aquarium_scopes_down_to_none(self, tmp_path):
        pm, path, entry = self._two_tank_project(tmp_path)

        assert pm.remove_aquarium_scope(path, 1, delete_files=False) is True
        multi = pm.get_multi_aquarium_zone_data(path)
        assert [aq.id for aq in multi.aquariums] == [0]
        assert list(entry["multi_aquarium_outputs"]) == ["0"]

        assert pm.remove_aquarium_scope(path, 0, delete_files=False) is True
        assert pm.get_multi_aquarium_zone_data(path) is None
        assert pm.remove_aquarium_scope(tmp_path / "ghost.mp4", 0) is False

    def test_clear_aquarium_subject_keeps_the_polygon(self, tmp_path):
        pm, path, entry = self._two_tank_project(tmp_path)

        assert pm.clear_aquarium_subject(path, 1, delete_analysis_data=False) is True

        aquarium = _reloaded_multi(pm, path).get_aquarium(1)
        assert (aquarium.subject_id, aquarium.polygon) == ("", SQUARE)  # type: ignore[union-attr]
        assert entry["multi_aquarium_outputs"]["1"]["subject_id"] == ""
        assert pm.clear_aquarium_subject(tmp_path / "ghost.mp4", 1) is False

    def test_reset_analysis_data(self, tmp_path):
        pm, path, entry = self._two_tank_project(tmp_path)

        assert pm.reset_analysis_data(path, aquarium_id=1, delete_files=False) is True
        assert entry["multi_aquarium_outputs"]["1"]["parquet_files"] == {}
        assert pm.reset_analysis_data(tmp_path / "ghost.mp4") is False


def _reloaded_multi(pm: ProjectManager, path: str) -> MultiAquariumZoneData:
    fresh = ProjectManager(settings_obj=None)
    fresh.load_project(pm.project_path)
    return fresh.get_multi_aquarium_zone_data(path)  # type: ignore[return-value]


class TestFacadeAssets:
    def test_remove_asset_branches(self, tmp_path):
        video = _video(tmp_path, "v.mp4")
        pm = _disk_project(tmp_path, video)
        entry = pm.find_video_entry(path=video["path"])
        entry.update(has_rois=True, has_trajectory=True, has_summary=True)  # type: ignore[union-attr]
        entry["parquet_files"] = {"trajectory": "t", "summary": "s"}  # type: ignore[index]

        assert pm.can_remove_asset(tmp_path / "ghost.mp4", "arena") == (
            False,
            "Video not found in the project.",
        )
        assert pm.remove_asset(tmp_path / "ghost.mp4", "rois") is False
        assert pm.remove_asset(video["path"], "summary", delete_files=False) is True
        assert pm.remove_asset(video["path"], "trajectory", delete_files=False) is True
        assert pm.remove_asset(video["path"], "rois", delete_files=False) is True
        saved = _reloaded(pm)["batches"][0]["videos"][0]
        assert (saved["has_rois"], saved["has_trajectory"], saved["has_summary"]) == (
            False,
            False,
            False,
        )
        assert pm.remove_asset(video["path"], "video", delete_files=False) is True
        assert _reloaded(pm)["batches"][0]["videos"] == []

    def test_small_delegates(self, tmp_path):
        video = _video(tmp_path, "v.mp4", group="A")
        pm = _disk_project(tmp_path, video)

        assert pm.get_project_type() == "Pre-recorded"
        assert pm.resolve_group_name("1", ["G01", "G02"]) == "G01"
        assert pm.get_multi_aquarium_zone_data(None) is None
        assert pm.is_multi_aquarium_video(None) is False
        assert pm.get_aquarium_count(None) == 1
        assert pm.get_aquarium_count(video["path"]) == 0
        pm.save_multi_aquarium_zone_data(None, MultiAquariumZoneData())
        pm.clear_multi_aquarium_zone_data(None)
        assert "multi_aquarium_zones" not in pm.project_data
        assert pm.get_analysis_profiles()[0]["name"] == "default"
        assert pm.resolve_analysis_profile({"group": "A"})["name"] == "default"
        assert ProjectManager._normalize_detector_thresholds({"conf_threshold": "0.4"}) == {
            "confidence_threshold": 0.4
        }
        assert pm.load_zones_from_parquet({"parquet_files": {}}) is None
        pm.save_last_session_details(5, "B")
        assert pm.get_last_session_details() == (5, "B")
        assert (_reloaded(pm)["last_selected_day"], _reloaded(pm)["last_selected_group"]) == (
            5,
            "B",
        )

    def test_multi_aquarium_outputs_make_a_video_multi(self, tmp_path):
        video = _video(tmp_path, "v.mp4")
        pm = _disk_project(tmp_path, video)
        entry = pm.find_video_entry(path=video["path"])
        entry["multi_aquarium_outputs"] = {"0": {}}  # type: ignore[index]
        assert pm.is_multi_aquarium_video(video["path"]) is False

        entry["multi_aquarium_outputs"]["1"] = {}  # type: ignore[index]

        assert pm.is_multi_aquarium_video(video["path"]) is True

    def test_zone_facade_round_trip(self, tmp_path):
        video = _video(tmp_path, "v.mp4")
        pm = _disk_project(tmp_path, video)
        pm.save_zone_data(ZoneData(polygon=SQUARE), video["path"])

        assert pm.has_zone_data(video["path"]) is True
        assert pm.get_last_zone_video() == ZoneManager.normalize_video_path(video["path"])
        clone = pm.clone_zone_data_from_video(Path(video["path"]))
        assert clone.polygon == SQUARE
        assert pm._resolve_zone_entry(video["path"])[1]["polygon"] == SQUARE  # type: ignore[index]
        exported = Path(pm.find_video_entry(path=video["path"])["parquet_files"]["arena"])  # type: ignore[index]
        assert exported.name == "1_ProcessingArea_v.parquet"
        assert exported.parent == Path(pm.project_path) / "Grupo_Sem_Grupo" / "Dia_Indefinido" / (  # type: ignore[arg-type]
            "Sujeito_Indefinido"
        )
        assert pm.resolve_zone_parquet_candidates(video["path"]) == {"arena": str(exported)}

        pm.clear_multi_aquarium_zone_data(video["path"])
        assert pm.has_zone_data(video["path"]) is False
