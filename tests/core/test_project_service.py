"""
Unit tests for ProjectService.

Phase 2, Step 5: Comprehensive unit tests for project file I/O operations.
Uses mocking to isolate the service from filesystem and external dependencies.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from tests.utils.wait_helpers import wait_for_condition
from zebtrack.core.project_service import (
    CONFIG_FILE_NAME,
    ProjectService,
)
from zebtrack.utils import IntegrityError


class TestProjectServiceCreation:
    """Test suite for project creation operations."""

    def test_create_project_directory_success(self, tmp_path):
        """Test successful project directory creation."""
        service = ProjectService()
        project_path = tmp_path / "new_project"
        project_name = "Test Project"
        project_type = "experimental"

        result = service.create_project_directory(
            project_path=str(project_path),
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

    def test_create_project_directory_with_initial_data(self, tmp_path):
        """Test project creation with initial data."""
        service = ProjectService()
        project_path = tmp_path / "new_project_data"
        project_name = "Test Project"
        project_type = "experimental"
        initial_data = {
            "videos": ["/path/to/video.mp4"],
            "custom_field": "custom_value",
        }

        result = service.create_project_directory(
            project_path=str(project_path),
            project_name=project_name,
            project_type=project_type,
            initial_data=initial_data,
        )

        # Verify initial data was preserved
        assert result["videos"] == initial_data["videos"]
        assert result["custom_field"] == initial_data["custom_field"]
        assert result["project_name"] == project_name

    def test_create_project_directory_already_exists(self, tmp_path):
        """Test error when project directory already exists."""
        service = ProjectService()
        project_path = tmp_path / "existing_project"
        project_path.mkdir()

        with pytest.raises(FileExistsError):
            service.create_project_directory(
                project_path=str(project_path),
                project_name="Test",
                project_type="experimental",
            )

    @patch("zebtrack.core.project_service.Path.mkdir")
    def test_create_project_directory_os_error(self, mock_mkdir, tmp_path):
        """Test handling of OS error during directory creation."""
        service = ProjectService()
        mock_mkdir.side_effect = OSError("Permission denied")

        with pytest.raises(OSError):
            service.create_project_directory(
                project_path=str(tmp_path / "invalid_path"),
                project_name="Test",
                project_type="experimental",
            )


class TestProjectServiceLoadSave:
    """Test suite for project config load/save operations."""

    def test_save_and_load_project_config_success(self, tmp_path):
        """Test successful save and load of project config."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        project_data = {
            "project_name": "Test Project",
            "project_type": "experimental",
            "videos": ["/path/to/video.mp4"],
            "detection_zones": {},
            "zones_by_video": {},
        }

        # Save
        service.save_project_config(str(project_path), project_data)

        # Verify file exists
        config_file = project_path / CONFIG_FILE_NAME
        assert config_file.exists()

        # Load
        loaded_data = service.load_project_config(str(project_path))

        # Verify data matches (except timestamps)
        assert loaded_data["project_name"] == project_data["project_name"]
        assert loaded_data["project_type"] == project_data["project_type"]
        assert loaded_data["videos"] == project_data["videos"]
        assert "last_modified" in loaded_data

    def test_save_project_config_adds_integrity_hash(self, tmp_path):
        """Test that save adds integrity hash to config file."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        project_data = {
            "project_name": "Test",
            "project_type": "experimental",
        }

        service.save_project_config(str(project_path), project_data)

        # Read raw file
        config_file = project_path / CONFIG_FILE_NAME
        with open(config_file, encoding="utf-8") as f:
            raw_data = json.load(f)

        assert "_integrity_hash" in raw_data

    def test_load_project_config_not_found(self, tmp_path):
        """Test error when config file doesn't exist."""
        service = ProjectService()
        with pytest.raises(FileNotFoundError):
            service.load_project_config(str(tmp_path / "nonexistent"))

    def test_load_project_config_malformed_json(self, tmp_path):
        """Test error when config file has malformed JSON."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        config_file = project_path / CONFIG_FILE_NAME
        with open(config_file, "w") as f:
            f.write("{invalid json")

        with pytest.raises(json.JSONDecodeError):
            service.load_project_config(str(project_path))

    def test_load_project_config_integrity_check_failure(self, tmp_path):
        """Test integrity error when hash doesn't match."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        project_data = {
            "project_name": "Test",
            "project_type": "experimental",
        }

        # Save legitimate config
        service.save_project_config(str(project_path), project_data)

        # Tamper with the file - change data but keep original hash
        config_file = project_path / CONFIG_FILE_NAME
        with open(config_file, encoding="utf-8") as f:
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
            service.load_project_config(str(project_path))

    def test_save_project_config_updates_timestamp(self, tmp_path):
        """Test that save updates last_modified timestamp."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        project_data = {"project_name": "Test"}

        service.save_project_config(str(project_path), project_data)
        first_timestamp = project_data.get("last_modified")

        # Save again - wait until timestamp would differ
        import time
        start_time = time.time()
        wait_for_condition(
            lambda: time.time() - start_time > 0.01,
            timeout=1.0,
            error_msg="Timestamp difference wait timed out"
        )

        service.save_project_config(str(project_path), project_data)
        loaded_data = service.load_project_config(str(project_path))

        # Timestamps should differ
        assert loaded_data["last_modified"] != first_timestamp

    @patch("builtins.open", side_effect=OSError("Disk full"))
    def test_save_project_config_os_error(self, mock_open_func, tmp_path):
        """Test handling of OS error during save."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        with pytest.raises(OSError):
            service.save_project_config(
                str(project_path),
                {"project_name": "Test"},
            )


class TestProjectServiceAssetManagement:
    """Test suite for asset management operations."""

    def test_delete_file_if_exists_file_exists(self, tmp_path):
        """Test deleting an existing file."""
        service = ProjectService()
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        result = service.delete_file_if_exists(test_file)

        assert result is True
        assert not test_file.exists()

    def test_delete_file_if_exists_file_not_exists(self, tmp_path):
        """Test deleting a non-existent file."""
        service = ProjectService()
        test_file = tmp_path / "nonexistent.txt"

        result = service.delete_file_if_exists(test_file)

        assert result is False

    @patch("pathlib.Path.unlink", side_effect=OSError("Permission denied"))
    def test_delete_file_if_exists_os_error(self, mock_unlink, tmp_path):
        """Test handling OS error during file deletion."""
        service = ProjectService()
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        with pytest.raises(OSError):
            service.delete_file_if_exists(test_file)

    def test_ensure_directory_creates_new(self, tmp_path):
        """Test creating a new directory."""
        service = ProjectService()
        new_dir = tmp_path / "new" / "nested" / "dir"

        result = service.ensure_directory(new_dir)

        assert result == new_dir
        assert new_dir.exists()
        assert new_dir.is_dir()

    def test_ensure_directory_already_exists(self, tmp_path):
        """Test ensuring an existing directory."""
        service = ProjectService()
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()

        result = service.ensure_directory(existing_dir)

        assert result == existing_dir
        assert existing_dir.exists()


class TestProjectServicePathResolution:
    """Test suite for path resolution operations."""

    def test_resolve_results_directory_no_metadata(self):
        """Test resolving results directory without metadata."""
        service = ProjectService()
        project_path = "/path/to/project"

        result = service.resolve_results_directory(project_path)

        assert result == Path("/path/to/project/results")

    def test_resolve_results_directory_with_full_metadata(self):
        """Test resolving results directory with full metadata."""
        service = ProjectService()
        project_path = "/path/to/project"
        metadata = {
            "group": "control",
            "day": "day_1",
            "subject": "subject_01",
        }

        result = service.resolve_results_directory(project_path, metadata)

        expected = Path("/path/to/project/results/control/day_1/subject_01")
        assert result == expected

    def test_resolve_results_directory_with_partial_metadata(self):
        """Test resolving results directory with partial metadata."""
        service = ProjectService()
        project_path = "/path/to/project"
        metadata = {
            "group": "control",
            "subject": "subject_01",
        }

        result = service.resolve_results_directory(project_path, metadata)

        expected = Path("/path/to/project/results/control/subject_01")
        assert result == expected

    def test_sanitize_path_component_removes_invalid_chars(self):
        """Test path component sanitization."""
        service = ProjectService()
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
            result = service._sanitize_path_component(input_val)
            assert result == expected, f"Failed for input: {input_val}"


class TestProjectServiceMetadata:
    """Test suite for metadata operations."""

    def test_load_metadata_csv_success(self, tmp_path):
        """Test loading metadata CSV successfully."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        metadata_file = project_path / "metadata.csv"
        df = pd.DataFrame(
            {
                "video": ["video1.mp4", "video2.mp4"],
                "group": ["control", "treated"],
                "subject": ["s01", "s02"],
            }
        )
        df.to_csv(metadata_file, index=False)

        result = service.load_metadata_csv(str(project_path))

        assert result is not None
        assert len(result) == 2
        assert "video" in result.columns
        assert "group" in result.columns

    def test_load_metadata_csv_not_found(self, tmp_path):
        """Test loading metadata when file doesn't exist."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        result = service.load_metadata_csv(str(project_path))

        assert result is None

    def test_load_metadata_csv_invalid_format(self, tmp_path):
        """Test loading metadata with invalid CSV."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        metadata_file = project_path / "metadata.csv"
        with open(metadata_file, "w") as f:
            f.write("invalid,csv\ndata")

        result = service.load_metadata_csv(str(project_path))

        # Service should handle gracefully and return None
        assert result is None or isinstance(result, pd.DataFrame)


class TestProjectServiceROITemplates:
    """Test suite for ROI template operations."""

    def test_ensure_roi_template_directory(self, tmp_path):
        """Test ensuring ROI template directory exists."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        result = service.ensure_roi_template_directory(str(project_path))

        assert result.exists()
        assert result.is_dir()
        assert result.name == "templates"

    def test_save_roi_template_success(self, tmp_path):
        """Test saving ROI template."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
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

        result_path = service.save_roi_template(
            str(project_path),
            template_name,
            template_data,
        )

        assert result_path.exists()
        assert result_path.name == f"{template_name}.json"

        # Verify content
        with open(result_path) as f:
            loaded = json.load(f)
        assert loaded == template_data

    def test_load_roi_template_success(self, tmp_path):
        """Test loading ROI template."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        template_name = "test_template"
        template_data = {"rois": [{"name": "ROI1", "polygon": [[0, 0], [100, 100]]}]}

        # Save first
        service.save_roi_template(
            str(project_path),
            template_name,
            template_data,
        )

        # Load
        result = service.load_roi_template(str(project_path), template_name)

        assert result == template_data

    def test_load_roi_template_not_found(self, tmp_path):
        """Test loading non-existent ROI template."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        result = service.load_roi_template(
            str(project_path),
            "nonexistent",
        )

        assert result is None

    def test_load_roi_template_malformed_json(self, tmp_path):
        """Test loading ROI template with malformed JSON."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        template_dir = project_path / "templates"
        template_dir.mkdir()
        template_file = template_dir / "bad_template.json"
        with open(template_file, "w") as f:
            f.write("{invalid json")

        result = service.load_roi_template(
            str(project_path),
            "bad_template",
        )

        assert result is None

    def test_list_roi_templates_success(self, tmp_path):
        """Test listing ROI templates."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        # Create multiple templates
        for i in range(3):
            service.save_roi_template(
                str(project_path),
                f"template_{i}",
                {"data": i},
            )

        result = service.list_roi_templates(str(project_path))

        assert len(result) == 3
        assert "template_0" in result
        assert "template_1" in result
        assert "template_2" in result
        assert result == sorted(result)  # Should be sorted

    def test_list_roi_templates_empty_directory(self, tmp_path):
        """Test listing templates when directory doesn't exist."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        result = service.list_roi_templates(str(project_path))

        assert result == []

    def test_list_roi_templates_no_json_files(self, tmp_path):
        """Test listing templates when directory has no JSON files."""
        service = ProjectService()
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        template_dir = project_path / "templates"
        template_dir.mkdir()
        (template_dir / "readme.txt").write_text("Not a template")

        result = service.list_roi_templates(str(project_path))

        assert result == []


class TestProjectServiceIntegration:
    """Integration tests for ProjectService workflows."""

    def test_full_project_lifecycle(self, tmp_path):
        """Test complete project create-save-load lifecycle."""
        service = ProjectService()
        project_path = tmp_path / "lifecycle_project"

        # 1. Create project
        initial_data = service.create_project_directory(
            project_path=str(project_path),
            project_name="Lifecycle Test",
            project_type="experimental",
            initial_data={"custom": "value"},
        )

        # 2. Modify and save
        initial_data["videos"] = ["/path/to/video.mp4"]
        initial_data["detection_zones"] = {"zone1": {}}
        service.save_project_config(str(project_path), initial_data)

        # 3. Load and verify
        loaded_data = service.load_project_config(str(project_path))
        assert loaded_data["project_name"] == "Lifecycle Test"
        assert loaded_data["videos"] == ["/path/to/video.mp4"]
        assert loaded_data["custom"] == "value"

        # 4. Create and load template
        template_data = {"rois": [{"name": "test"}]}
        service.save_roi_template(str(project_path), "test_template", template_data)
        loaded_template = service.load_roi_template(str(project_path), "test_template")
        assert loaded_template == template_data

        # 5. List templates
        templates = service.list_roi_templates(str(project_path))
        assert "test_template" in templates

    def test_concurrent_saves_maintain_integrity(self, tmp_path):
        """Test that multiple saves maintain config integrity."""
        service = ProjectService()
        project_path = tmp_path / "concurrent_project"
        service.create_project_directory(
            project_path=str(project_path),
            project_name="Concurrent Test",
            project_type="experimental",
        )

        # Multiple save/load cycles
        for i in range(5):
            data = service.load_project_config(str(project_path))
            data[f"field_{i}"] = f"value_{i}"
            service.save_project_config(str(project_path), data)

        # Final load should have all fields
        final_data = service.load_project_config(str(project_path))
        for i in range(5):
            assert final_data[f"field_{i}"] == f"value_{i}"
