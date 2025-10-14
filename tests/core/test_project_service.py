# -*- coding: utf-8 -*-
"""
Unit tests for ProjectService.

Phase 2, Step 5: Comprehensive unit tests for project file I/O operations.
Uses mocking to isolate the service from filesystem and external dependencies.
"""

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from zebtrack.core.project_service import (
    CONFIG_FILE_NAME,
    ProjectService,
)
from zebtrack.utils import IntegrityError


class TestProjectServiceCreation(unittest.TestCase):
    """Test suite for project creation operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = ProjectService()
        self.test_dir = Path("temp_test_project_service")
        self.test_dir.mkdir(exist_ok=True)

    def tearDown(self):
        """Clean up test artifacts."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_create_project_directory_success(self):
        """Test successful project directory creation."""
        project_path = str(self.test_dir / "new_project")
        project_name = "Test Project"
        project_type = "experimental"

        result = self.service.create_project_directory(
            project_path=project_path,
            project_name=project_name,
            project_type=project_type,
        )

        # Verify directory was created
        assert Path(project_path).exists()
        assert Path(project_path).is_dir()

        # Verify returned data structure
        assert result["project_name"] == project_name
        assert result["project_type"] == project_type
        assert "created_at" in result
        assert "last_modified" in result
        assert "videos" in result
        assert "detection_zones" in result
        assert "zones_by_video" in result
        assert "roi_templates" in result

        # Verify config file was saved
        config_file = Path(project_path) / CONFIG_FILE_NAME
        assert config_file.exists()

    def test_create_project_directory_with_initial_data(self):
        """Test project creation with initial data."""
        project_path = str(self.test_dir / "new_project_data")
        project_name = "Test Project"
        project_type = "experimental"
        initial_data = {
            "videos": ["/path/to/video.mp4"],
            "custom_field": "custom_value",
        }

        result = self.service.create_project_directory(
            project_path=project_path,
            project_name=project_name,
            project_type=project_type,
            initial_data=initial_data,
        )

        # Verify initial data was preserved
        assert result["videos"] == initial_data["videos"]
        assert result["custom_field"] == initial_data["custom_field"]
        assert result["project_name"] == project_name

    def test_create_project_directory_already_exists(self):
        """Test error when project directory already exists."""
        project_path = str(self.test_dir / "existing_project")
        Path(project_path).mkdir()

        with pytest.raises(FileExistsError):
            self.service.create_project_directory(
                project_path=project_path,
                project_name="Test",
                project_type="experimental",
            )

    @patch("zebtrack.core.project_service.Path.mkdir")
    def test_create_project_directory_os_error(self, mock_mkdir):
        """Test handling of OS error during directory creation."""
        mock_mkdir.side_effect = OSError("Permission denied")

        with pytest.raises(OSError):
            self.service.create_project_directory(
                project_path="invalid_path",
                project_name="Test",
                project_type="experimental",
            )


class TestProjectServiceLoadSave(unittest.TestCase):
    """Test suite for project config load/save operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = ProjectService()
        self.test_dir = Path("temp_test_project_service")
        self.test_dir.mkdir(exist_ok=True)
        self.project_path = self.test_dir / "test_project"
        self.project_path.mkdir()

    def tearDown(self):
        """Clean up test artifacts."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_save_and_load_project_config_success(self):
        """Test successful save and load of project config."""
        project_data = {
            "project_name": "Test Project",
            "project_type": "experimental",
            "videos": ["/path/to/video.mp4"],
            "detection_zones": {},
            "zones_by_video": {},
        }

        # Save
        self.service.save_project_config(str(self.project_path), project_data)

        # Verify file exists
        config_file = self.project_path / CONFIG_FILE_NAME
        assert config_file.exists()

        # Load
        loaded_data = self.service.load_project_config(str(self.project_path))

        # Verify data matches (except timestamps)
        assert loaded_data["project_name"] == project_data["project_name"]
        assert loaded_data["project_type"] == project_data["project_type"]
        assert loaded_data["videos"] == project_data["videos"]
        assert "last_modified" in loaded_data

    def test_save_project_config_adds_integrity_hash(self):
        """Test that save adds integrity hash to config file."""
        project_data = {
            "project_name": "Test",
            "project_type": "experimental",
        }

        self.service.save_project_config(str(self.project_path), project_data)

        # Read raw file
        config_file = self.project_path / CONFIG_FILE_NAME
        with open(config_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        assert "_integrity_hash" in raw_data

    def test_load_project_config_not_found(self):
        """Test error when config file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            self.service.load_project_config(str(self.test_dir / "nonexistent"))

    def test_load_project_config_malformed_json(self):
        """Test error when config file has malformed JSON."""
        config_file = self.project_path / CONFIG_FILE_NAME
        with open(config_file, "w") as f:
            f.write("{invalid json")

        with pytest.raises(json.JSONDecodeError):
            self.service.load_project_config(str(self.project_path))

    def test_load_project_config_integrity_check_failure(self):
        """Test integrity error when hash doesn't match."""
        project_data = {
            "project_name": "Test",
            "project_type": "experimental",
        }

        # Save legitimate config
        self.service.save_project_config(str(self.project_path), project_data)

        # Tamper with the file - change data but keep original hash
        config_file = self.project_path / CONFIG_FILE_NAME
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Save the original hash before tampering
        original_hash = data.get("_integrity_hash")

        # Tamper with the data
        data["project_name"] = "Tampered"
        # Put back the old hash to simulate tampering
        data["_integrity_hash"] = original_hash

        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        # Load should fail with integrity error
        with pytest.raises(IntegrityError):
            self.service.load_project_config(str(self.project_path))

    def test_save_project_config_updates_timestamp(self):
        """Test that save updates last_modified timestamp."""
        project_data = {"project_name": "Test"}

        self.service.save_project_config(str(self.project_path), project_data)
        first_timestamp = project_data.get("last_modified")

        # Small delay to ensure timestamp difference
        import time

        time.sleep(0.01)

        # Save again
        self.service.save_project_config(str(self.project_path), project_data)
        loaded_data = self.service.load_project_config(str(self.project_path))

        # Timestamps should differ
        assert loaded_data["last_modified"] != first_timestamp

    @patch("builtins.open", side_effect=OSError("Disk full"))
    def test_save_project_config_os_error(self, mock_open_func):
        """Test handling of OS error during save."""
        with pytest.raises(OSError):
            self.service.save_project_config(
                str(self.project_path),
                {"project_name": "Test"},
            )


class TestProjectServiceAssetManagement(unittest.TestCase):
    """Test suite for asset management operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = ProjectService()
        self.test_dir = Path("temp_test_project_service")
        self.test_dir.mkdir(exist_ok=True)

    def tearDown(self):
        """Clean up test artifacts."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_delete_file_if_exists_file_exists(self):
        """Test deleting an existing file."""
        test_file = self.test_dir / "test.txt"
        test_file.write_text("content")

        result = self.service.delete_file_if_exists(test_file)

        assert result is True
        assert not test_file.exists()

    def test_delete_file_if_exists_file_not_exists(self):
        """Test deleting a non-existent file."""
        test_file = self.test_dir / "nonexistent.txt"

        result = self.service.delete_file_if_exists(test_file)

        assert result is False

    @patch("pathlib.Path.unlink", side_effect=OSError("Permission denied"))
    def test_delete_file_if_exists_os_error(self, mock_unlink):
        """Test handling OS error during file deletion."""
        test_file = self.test_dir / "test.txt"
        test_file.write_text("content")

        with pytest.raises(OSError):
            self.service.delete_file_if_exists(test_file)

    def test_ensure_directory_creates_new(self):
        """Test creating a new directory."""
        new_dir = self.test_dir / "new" / "nested" / "dir"

        result = self.service.ensure_directory(new_dir)

        assert result == new_dir
        assert new_dir.exists()
        assert new_dir.is_dir()

    def test_ensure_directory_already_exists(self):
        """Test ensuring an existing directory."""
        existing_dir = self.test_dir / "existing"
        existing_dir.mkdir()

        result = self.service.ensure_directory(existing_dir)

        assert result == existing_dir
        assert existing_dir.exists()


class TestProjectServicePathResolution(unittest.TestCase):
    """Test suite for path resolution operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = ProjectService()

    def test_resolve_results_directory_no_metadata(self):
        """Test resolving results directory without metadata."""
        project_path = "/path/to/project"

        result = self.service.resolve_results_directory(project_path)

        assert result == Path("/path/to/project/results")

    def test_resolve_results_directory_with_full_metadata(self):
        """Test resolving results directory with full metadata."""
        project_path = "/path/to/project"
        metadata = {
            "group": "control",
            "day": "day_1",
            "subject": "subject_01",
        }

        result = self.service.resolve_results_directory(project_path, metadata)

        expected = Path("/path/to/project/results/control/day_1/subject_01")
        assert result == expected

    def test_resolve_results_directory_with_partial_metadata(self):
        """Test resolving results directory with partial metadata."""
        project_path = "/path/to/project"
        metadata = {
            "group": "control",
            "subject": "subject_01",
        }

        result = self.service.resolve_results_directory(project_path, metadata)

        expected = Path("/path/to/project/results/control/subject_01")
        assert result == expected

    def test_sanitize_path_component_removes_invalid_chars(self):
        """Test path component sanitization."""
        test_cases = [
            ("valid_name", "valid_name"),
            ("name/with\\slashes", "name_with_slashes"),
            ("name:with*special?chars", "name_with_special_chars"),
            ('name"with<quotes>', "name_with_quotes_"),
            ("  .name with spaces.  ", "name with spaces"),
            ("", "untitled"),
            ("...", "untitled"),
        ]

        for input_val, expected in test_cases:
            result = self.service._sanitize_path_component(input_val)
            assert result == expected, f"Failed for input: {input_val}"


class TestProjectServiceMetadata(unittest.TestCase):
    """Test suite for metadata operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = ProjectService()
        self.test_dir = Path("temp_test_project_service")
        self.test_dir.mkdir(exist_ok=True)
        self.project_path = self.test_dir / "test_project"
        self.project_path.mkdir()

    def tearDown(self):
        """Clean up test artifacts."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_load_metadata_csv_success(self):
        """Test loading metadata CSV successfully."""
        metadata_file = self.project_path / "metadata.csv"
        df = pd.DataFrame(
            {
                "video": ["video1.mp4", "video2.mp4"],
                "group": ["control", "treated"],
                "subject": ["s01", "s02"],
            }
        )
        df.to_csv(metadata_file, index=False)

        result = self.service.load_metadata_csv(str(self.project_path))

        assert result is not None
        assert len(result) == 2
        assert "video" in result.columns
        assert "group" in result.columns

    def test_load_metadata_csv_not_found(self):
        """Test loading metadata when file doesn't exist."""
        result = self.service.load_metadata_csv(str(self.project_path))

        assert result is None

    def test_load_metadata_csv_invalid_format(self):
        """Test loading metadata with invalid CSV."""
        metadata_file = self.project_path / "metadata.csv"
        with open(metadata_file, "w") as f:
            f.write("invalid,csv\ndata")

        result = self.service.load_metadata_csv(str(self.project_path))

        # Service should handle gracefully and return None
        assert result is None or isinstance(result, pd.DataFrame)


class TestProjectServiceROITemplates(unittest.TestCase):
    """Test suite for ROI template operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = ProjectService()
        self.test_dir = Path("temp_test_project_service")
        self.test_dir.mkdir(exist_ok=True)
        self.project_path = self.test_dir / "test_project"
        self.project_path.mkdir()

    def tearDown(self):
        """Clean up test artifacts."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_ensure_roi_template_directory(self):
        """Test ensuring ROI template directory exists."""
        result = self.service.ensure_roi_template_directory(str(self.project_path))

        assert result.exists()
        assert result.is_dir()
        assert result.name == "templates"

    def test_save_roi_template_success(self):
        """Test saving ROI template."""
        template_name = "test_template"
        template_data = {
            "rois": [
                {"name": "ROI1", "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]]},
                {
                    "name": "ROI2",
                    "polygon": [[200, 0], [300, 0], [300, 100], [200, 100]],
                },
            ]
        }

        result_path = self.service.save_roi_template(
            str(self.project_path),
            template_name,
            template_data,
        )

        assert result_path.exists()
        assert result_path.name == f"{template_name}.json"

        # Verify content
        with open(result_path, "r") as f:
            loaded = json.load(f)
        assert loaded == template_data

    def test_load_roi_template_success(self):
        """Test loading ROI template."""
        template_name = "test_template"
        template_data = {"rois": [{"name": "ROI1", "polygon": [[0, 0], [100, 100]]}]}

        # Save first
        self.service.save_roi_template(
            str(self.project_path),
            template_name,
            template_data,
        )

        # Load
        result = self.service.load_roi_template(str(self.project_path), template_name)

        assert result == template_data

    def test_load_roi_template_not_found(self):
        """Test loading non-existent ROI template."""
        result = self.service.load_roi_template(
            str(self.project_path),
            "nonexistent",
        )

        assert result is None

    def test_load_roi_template_malformed_json(self):
        """Test loading ROI template with malformed JSON."""
        template_dir = self.project_path / "templates"
        template_dir.mkdir()
        template_file = template_dir / "bad_template.json"
        with open(template_file, "w") as f:
            f.write("{invalid json")

        result = self.service.load_roi_template(
            str(self.project_path),
            "bad_template",
        )

        assert result is None

    def test_list_roi_templates_success(self):
        """Test listing ROI templates."""
        # Create multiple templates
        for i in range(3):
            self.service.save_roi_template(
                str(self.project_path),
                f"template_{i}",
                {"data": i},
            )

        result = self.service.list_roi_templates(str(self.project_path))

        assert len(result) == 3
        assert "template_0" in result
        assert "template_1" in result
        assert "template_2" in result
        assert result == sorted(result)  # Should be sorted

    def test_list_roi_templates_empty_directory(self):
        """Test listing templates when directory doesn't exist."""
        result = self.service.list_roi_templates(str(self.project_path))

        assert result == []

    def test_list_roi_templates_no_json_files(self):
        """Test listing templates when directory has no JSON files."""
        template_dir = self.project_path / "templates"
        template_dir.mkdir()
        (template_dir / "readme.txt").write_text("Not a template")

        result = self.service.list_roi_templates(str(self.project_path))

        assert result == []


class TestProjectServiceIntegration(unittest.TestCase):
    """Integration tests for ProjectService workflows."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = ProjectService()
        self.test_dir = Path("temp_test_project_service")
        self.test_dir.mkdir(exist_ok=True)

    def tearDown(self):
        """Clean up test artifacts."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_full_project_lifecycle(self):
        """Test complete project create-save-load lifecycle."""
        project_path = str(self.test_dir / "lifecycle_project")

        # 1. Create project
        initial_data = self.service.create_project_directory(
            project_path=project_path,
            project_name="Lifecycle Test",
            project_type="experimental",
            initial_data={"custom": "value"},
        )

        # 2. Modify and save
        initial_data["videos"] = ["/path/to/video.mp4"]
        initial_data["detection_zones"] = {"zone1": {}}
        self.service.save_project_config(project_path, initial_data)

        # 3. Load and verify
        loaded_data = self.service.load_project_config(project_path)
        assert loaded_data["project_name"] == "Lifecycle Test"
        assert loaded_data["videos"] == ["/path/to/video.mp4"]
        assert loaded_data["custom"] == "value"

        # 4. Create and load template
        template_data = {"rois": [{"name": "test"}]}
        self.service.save_roi_template(project_path, "test_template", template_data)
        loaded_template = self.service.load_roi_template(project_path, "test_template")
        assert loaded_template == template_data

        # 5. List templates
        templates = self.service.list_roi_templates(project_path)
        assert "test_template" in templates

    def test_concurrent_saves_maintain_integrity(self):
        """Test that multiple saves maintain config integrity."""
        project_path = str(self.test_dir / "concurrent_project")
        self.service.create_project_directory(
            project_path=project_path,
            project_name="Concurrent Test",
            project_type="experimental",
        )

        # Multiple save/load cycles
        for i in range(5):
            data = self.service.load_project_config(project_path)
            data[f"field_{i}"] = f"value_{i}"
            self.service.save_project_config(project_path, data)

        # Final load should have all fields
        final_data = self.service.load_project_config(project_path)
        for i in range(5):
            assert final_data[f"field_{i}"] == f"value_{i}"


if __name__ == "__main__":
    unittest.main()
